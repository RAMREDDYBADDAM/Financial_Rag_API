"""
Background Task Queue Management
=================================
Provides async task processing with status tracking for long-running operations.

Features:
- UUID-based task identification
- Status tracking: pending, running, completed, failed
- Thread-safe task execution
- Result and error storage
- Timestamp tracking for auditing
"""

import uuid
import asyncio
from typing import Dict, Any, Optional, Callable, Awaitable
from datetime import datetime
from enum import Enum
import traceback
import logging

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskNotFoundError(Exception):
    """Raised when task ID is not found in queue."""
    pass


class QueryQueue:
    """
    Background task queue for async query processing.
    
    Thread-safe task management with status tracking and result storage.
    Designed for long-running LLM queries that exceed typical HTTP timeout.
    
    Example:
        queue = QueryQueue()
        task_id = await queue.add_task(process_complex_query, question="What is...")
        status = queue.get_task_status(task_id)
    """
    
    def __init__(self):
        """Initialize empty task queue."""
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def add_task(
        self,
        task_fn: Callable[..., Awaitable[Any]],
        *args,
        **kwargs
    ) -> str:
        """
        Add a new task to the queue and start execution.
        
        Args:
            task_fn: Async function to execute
            *args: Positional arguments for task_fn
            **kwargs: Keyword arguments for task_fn
        
        Returns:
            str: UUID task identifier
        
        Example:
            task_id = await queue.add_task(
                answer_financial_question,
                user_id="user123",
                question="Analyze market trends"
            )
        """
        task_id = str(uuid.uuid4())
        
        async with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "status": TaskStatus.PENDING,
                "result": None,
                "error": None,
                "created_at": datetime.utcnow().isoformat(),
                "started_at": None,
                "completed_at": None,
                "function_name": task_fn.__name__ if hasattr(task_fn, "__name__") else "unknown",
            }
        
        # Start task execution in background
        asyncio.create_task(self._execute_task(task_id, task_fn, *args, **kwargs))
        
        logger.info(f"Task {task_id} added to queue: {task_fn.__name__}")
        return task_id
    
    async def _execute_task(
        self,
        task_id: str,
        task_fn: Callable[..., Awaitable[Any]],
        *args,
        **kwargs
    ) -> None:
        """
        Execute task and update status.
        
        Internal method that handles task lifecycle:
        1. Update status to RUNNING
        2. Execute task function
        3. Store result or error
        4. Update status to COMPLETED or FAILED
        
        Args:
            task_id: Task identifier
            task_fn: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
        """
        try:
            # Update to RUNNING status
            async with self._lock:
                if task_id in self._tasks:
                    self._tasks[task_id]["status"] = TaskStatus.RUNNING
                    self._tasks[task_id]["started_at"] = datetime.utcnow().isoformat()
            
            logger.info(f"Task {task_id} started execution")
            
            # Execute the task function
            result = await task_fn(*args, **kwargs)
            
            # Store successful result
            async with self._lock:
                if task_id in self._tasks:
                    self._tasks[task_id]["status"] = TaskStatus.COMPLETED
                    self._tasks[task_id]["result"] = result
                    self._tasks[task_id]["completed_at"] = datetime.utcnow().isoformat()
            
            logger.info(f"Task {task_id} completed successfully")
            
        except Exception as e:
            # Store error information
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc()
            }
            
            async with self._lock:
                if task_id in self._tasks:
                    self._tasks[task_id]["status"] = TaskStatus.FAILED
                    self._tasks[task_id]["error"] = error_details
                    self._tasks[task_id]["completed_at"] = datetime.utcnow().isoformat()
            
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get current status and details for a task.
        
        Args:
            task_id: Task identifier
        
        Returns:
            Dict containing:
                - task_id: UUID identifier
                - status: Current status (pending/running/completed/failed)
                - result: Task result if completed
                - error: Error details if failed
                - created_at: ISO timestamp
                - started_at: ISO timestamp (if started)
                - completed_at: ISO timestamp (if finished)
                - function_name: Name of executed function
        
        Raises:
            TaskNotFoundError: If task_id not found
        
        Example:
            status = queue.get_task_status("123e4567-e89b-12d3-a456-426614174000")
            if status["status"] == "completed":
                print(status["result"])
        """
        if task_id not in self._tasks:
            raise TaskNotFoundError(f"Task {task_id} not found in queue")
        
        return self._tasks[task_id].copy()
    
    def list_tasks(self, status_filter: Optional[TaskStatus] = None) -> list[Dict[str, Any]]:
        """
        List all tasks, optionally filtered by status.
        
        Args:
            status_filter: Only return tasks with this status
        
        Returns:
            List of task status dictionaries
        
        Example:
            # Get all running tasks
            running = queue.list_tasks(TaskStatus.RUNNING)
        """
        tasks = list(self._tasks.values())
        
        if status_filter:
            tasks = [t for t in tasks if t["status"] == status_filter]
        
        return tasks
    
    async def clear_completed(self, max_age_seconds: int = 3600) -> int:
        """
        Remove completed/failed tasks older than max_age.
        
        Args:
            max_age_seconds: Remove tasks completed more than this many seconds ago
        
        Returns:
            int: Number of tasks removed
        
        Example:
            # Clean up tasks older than 1 hour
            removed = await queue.clear_completed(3600)
        """
        now = datetime.utcnow()
        to_remove = []
        
        async with self._lock:
            for task_id, task in self._tasks.items():
                if task["status"] in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                    if task["completed_at"]:
                        completed = datetime.fromisoformat(task["completed_at"])
                        age_seconds = (now - completed).total_seconds()
                        if age_seconds > max_age_seconds:
                            to_remove.append(task_id)
            
            for task_id in to_remove:
                del self._tasks[task_id]
        
        if to_remove:
            logger.info(f"Cleared {len(to_remove)} old tasks from queue")
        
        return len(to_remove)
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics.
        
        Returns:
            Dict with counts by status and total tasks
        
        Example:
            stats = queue.get_queue_stats()
            # {"total": 10, "pending": 2, "running": 3, "completed": 4, "failed": 1}
        """
        stats = {
            "total": len(self._tasks),
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
        }
        
        for task in self._tasks.values():
            status = task["status"]
            if status == TaskStatus.PENDING:
                stats["pending"] += 1
            elif status == TaskStatus.RUNNING:
                stats["running"] += 1
            elif status == TaskStatus.COMPLETED:
                stats["completed"] += 1
            elif status == TaskStatus.FAILED:
                stats["failed"] += 1
        
        return stats


# Global singleton instance
_global_queue: Optional[QueryQueue] = None


def get_query_queue() -> QueryQueue:
    """
    Get global QueryQueue singleton instance.
    
    Returns:
        QueryQueue: Global queue instance
    
    Example:
        from app.core.queue import get_query_queue
        queue = get_query_queue()
        task_id = await queue.add_task(my_function, arg1, arg2)
    """
    global _global_queue
    if _global_queue is None:
        _global_queue = QueryQueue()
    return _global_queue

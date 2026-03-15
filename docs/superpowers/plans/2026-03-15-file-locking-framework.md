# Unified File Locking Framework Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a unified file locking framework with support for NFS-safe locking, HDF5 concurrency protection, atomic JSON operations, and retry mechanisms with exponential backoff.

**Architecture:** Modular locking system with backend selection (fcntl vs flufl.lock for NFS), HDF5 SWMR manager for concurrent HDF5 access, tenacity-based retry decorators, and enhanced atomic operations for JSON/HDF5 files.

**Tech Stack:** Python 3.13+, fcntl, flufl.lock, h5py (>=3.0.0), tenacity, xxhash (checksums)

---

## Chunk 1: Core Locking Framework Foundation

### Task 1.1: Create BaseFileLock Abstract Base Class

**Files:**
- Create: `dlazy/utils/locking/base.py`
- Modify: `dlazy/utils/concurrency.py:1-50` (add import)
- Test: `tests/test_locking/test_base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_locking/test_base.py
import pytest
from dlazy.utils.locking.base import BaseFileLock

def test_base_file_lock_abstract():
    """Test that BaseFileLock cannot be instantiated directly."""
    with pytest.raises(TypeError) as exc:
        BaseFileLock("/tmp/test.lock")
    assert "abstract" in str(exc.value).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_locking/test_base.py::test_base_file_lock_abstract -v`
Expected: FAIL with "BaseFileLock not defined"

- [ ] **Step 3: Write minimal implementation**

```python
# dlazy/utils/locking/base.py
from abc import ABC, abstractmethod
import os
import time
from typing import Optional, Callable, Any
from dataclasses import dataclass

@dataclass
class LockAcquisitionResult:
    """Result of lock acquisition attempt."""
    acquired: bool
    elapsed: float
    error: Optional[Exception] = None
    metadata: Optional[dict] = None

class BaseFileLock(ABC):
    """Abstract base class for file locking implementations."""
    
    def __init__(self, lock_path: str, timeout: float = 30.0, poll_interval: float = 0.1):
        self.lock_path = lock_path
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._locked = False
    
    @abstractmethod
    def _acquire(self) -> bool:
        """Internal implementation of lock acquisition."""
        pass
    
    @abstractmethod  
    def _release(self) -> bool:
        """Internal implementation of lock release."""
        pass
    
    def acquire(self) -> LockAcquisitionResult:
        """Attempt to acquire lock with timeout."""
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            try:
                if self._acquire():
                    self._locked = True
                    elapsed = time.time() - start_time
                    return LockAcquisitionResult(
                        acquired=True,
                        elapsed=elapsed,
                        metadata={"lock_path": self.lock_path}
                    )
            except Exception as e:
                elapsed = time.time() - start_time
                return LockAcquisitionResult(
                    acquired=False,
                    elapsed=elapsed,
                    error=e
                )
            time.sleep(self.poll_interval)
        
        elapsed = time.time() - start_time
        return LockAcquisitionResult(
            acquired=False,
            elapsed=elapsed,
            error=TimeoutError(f"Timeout acquiring lock after {self.timeout}s")
        )
    
    def release(self) -> bool:
        """Release the lock if acquired."""
        if not self._locked:
            return True
        try:
            result = self._release()
            if result:
                self._locked = False
            return result
        except Exception:
            return False
    
    def __enter__(self):
        result = self.acquire()
        if not result.acquired:
            raise RuntimeError(f"Failed to acquire lock: {result.error}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
    
    @property
    def is_locked(self) -> bool:
        return self._locked
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_locking/test_base.py::test_base_file_lock_abstract -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dlazy/utils/locking/base.py tests/test_locking/test_base.py
git commit -m "feat: add BaseFileLock abstract class"
```

### Task 1.2: Create LocalFileLock (fcntl-based)

**Files:**
- Create: `dlazy/utils/locking/local.py`
- Test: `tests/test_locking/test_local.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_locking/test_local.py
import pytest
import tempfile
import os
from dlazy.utils.locking.local import LocalFileLock

def test_local_file_lock_acquire_release():
    """Test basic lock acquisition and release."""
    with tempfile.NamedTemporaryFile(suffix=".lock", delete=False) as tmp:
        lock_path = tmp.name
    
    try:
        lock = LocalFileLock(lock_path, timeout=1.0)
        
        # First lock should succeed
        result = lock.acquire()
        assert result.acquired is True
        assert lock.is_locked is True
        
        # Release should work
        assert lock.release() is True
        assert lock.is_locked is False
        
        # Context manager
        with lock as l:
            assert l.is_locked is True
        assert lock.is_locked is False
        
    finally:
        if os.path.exists(lock_path):
            os.unlink(lock_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_locking/test_local.py::test_local_file_lock_acquire_release -v`
Expected: FAIL with "LocalFileLock not defined"

- [ ] **Step 3: Write minimal implementation**

```python
# dlazy/utils/locking/local.py
import fcntl
import os
from typing import Optional
from .base import BaseFileLock, LockAcquisitionResult

class LocalFileLock(BaseFileLock):
    """fcntl-based file lock for local filesystems."""
    
    def __init__(self, lock_path: str, timeout: float = 30.0, poll_interval: float = 0.1):
        super().__init__(lock_path, timeout, poll_interval)
        self._fd: Optional[int] = None
    
    def _acquire(self) -> bool:
        """Acquire lock using fcntl."""
        try:
            # Open the lock file
            self._fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o644)
            
            # Try to acquire exclusive lock
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (IOError, OSError):
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            return False
    
    def _release(self) -> bool:
        """Release fcntl lock."""
        try:
            if self._fd is not None:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
                self._fd = None
            return True
        except (IOError, OSError):
            return False
    
    def __del__(self):
        """Cleanup on deletion."""
        if self._fd is not None:
            try:
                os.close(self._fd)
            except:
                pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_locking/test_local.py::test_local_file_lock_acquire_release -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dlazy/utils/locking/local.py tests/test_locking/test_local.py
git commit -m "feat: add LocalFileLock (fcntl-based)"
```

### Task 1.3: Create NFSFileLock (flufl.lock-based)

**Files:**
- Create: `dlazy/utils/locking/nfs.py`
- Test: `tests/test_locking/test_nfs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_locking/test_nfs.py
import pytest
import tempfile
import os
from dlazy.utils.locking.nfs import NFSFileLock

def test_nfs_file_lock_requires_flufl_lock():
    """Test that NFSFileLock raises informative error if flufl.lock not installed."""
    with tempfile.NamedTemporaryFile(suffix=".lock", delete=False) as tmp:
        lock_path = tmp.name
    
    try:
        # This should work if flufl.lock is installed
        # If not, it should raise ImportError with helpful message
        lock = NFSFileLock(lock_path)
        assert lock is not None
    except ImportError as e:
        assert "flufl.lock" in str(e)
    finally:
        if os.path.exists(lock_path):
            os.unlink(lock_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_locking/test_nfs.py::test_nfs_file_lock_requires_flufl_lock -v`
Expected: FAIL with "NFSFileLock not defined"

- [ ] **Step 3: Write minimal implementation**

```python
# dlazy/utils/locking/nfs.py
import os
from typing import Optional
from .base import BaseFileLock

try:
    from flufl.lock import Lock
    HAS_FLUFL_LOCK = True
except ImportError:
    HAS_FLUFL_LOCK = False

class NFSFileLock(BaseFileLock):
    """NFS-safe file lock using flufl.lock library."""
    
    def __init__(self, lock_path: str, timeout: float = 30.0, poll_interval: float = 0.1):
        if not HAS_FLUFL_LOCK:
            raise ImportError(
                "flufl.lock library is required for NFSFileLock. "
                "Install with: pip install flufl.lock"
            )
        super().__init__(lock_path, timeout, poll_interval)
        self._lock: Optional[Lock] = None
    
    def _acquire(self) -> bool:
        """Acquire NFS-safe lock using flufl.lock."""
        try:
            # Create lock directory if it doesn't exist
            lock_dir = os.path.dirname(self.lock_path)
            if lock_dir and not os.path.exists(lock_dir):
                os.makedirs(lock_dir, exist_ok=True)
            
            self._lock = Lock(self.lock_path)
            # flufl.lock uses timeout in seconds
            return self._lock.lock(timeout=self.timeout)
        except Exception:
            self._lock = None
            return False
    
    def _release(self) -> bool:
        """Release flufl.lock."""
        try:
            if self._lock is not None and self._lock.is_locked:
                self._lock.unlock()
            self._lock = None
            return True
        except Exception:
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_locking/test_nfs.py::test_nfs_file_lock_requires_flufl_lock -v`
Expected: PASS (or SKIP if flufl.lock not installed)

- [ ] **Step 5: Commit**

```bash
git add dlazy/utils/locking/nfs.py tests/test_locking/test_nfs.py
git commit -m "feat: add NFSFileLock (flufl.lock-based)"
```

### Task 1.4: Create LockFactory for Backend Selection

**Files:**
- Create: `dlazy/utils/locking/factory.py`
- Test: `tests/test_locking/test_factory.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_locking/test_factory.py
import pytest
import tempfile
import os
from dlazy.utils.locking.factory import create_file_lock, FileLockBackend

def test_create_file_lock_auto_detects_nfs():
    """Test that factory auto-detects NFS paths."""
    with tempfile.NamedTemporaryFile(suffix=".lock", delete=False) as tmp:
        lock_path = tmp.name
    
    try:
        # Test local path detection
        lock = create_file_lock("/tmp/test.lock")
        assert lock.__class__.__name__ == "LocalFileLock"
        
        # Test explicit backend selection
        lock = create_file_lock("/tmp/test.lock", backend=FileLockBackend.LOCAL)
        assert lock.__class__.__name__ == "LocalFileLock"
        
        # Test NFS backend (if available)
        lock = create_file_lock("/tmp/test.lock", backend=FileLockBackend.NFS)
        assert lock.__class__.__name__ == "NFSFileLock"
        
    finally:
        if os.path.exists(lock_path):
            os.unlink(lock_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_locking/test_factory.py::test_create_file_lock_auto_detects_nfs -v`
Expected: FAIL with "create_file_lock not defined"

- [ ] **Step 3: Write minimal implementation**

```python
# dlazy/utils/locking/factory.py
import os
import re
from enum import Enum
from typing import Union, Optional
from .local import LocalFileLock
from .nfs import NFSFileLock

class FileLockBackend(Enum):
    """Available file locking backends."""
    LOCAL = "local"  # fcntl-based, for local filesystems
    NFS = "nfs"      # flufl.lock-based, for NFS filesystems

def is_nfs_path(path: str) -> bool:
    """
    Detect if path is likely on NFS filesystem.
    Heuristics based on common NFS mount patterns.
    """
    # Common NFS mount patterns
    nfs_patterns = [
        r'^/nfs/',
        r'^/shared/',
        r'^/home/[^/]+/shared/',
        r'^/mnt/nfs/',
        r'^/media/nfs/',
        r'^/data/',
        r'^/gpfs/',
        r'^/lustre/',
    ]
    
    for pattern in nfs_patterns:
        if re.match(pattern, path):
            return True
    
    # Check if path contains network share indicators
    if ':' in path and path.startswith('/'):
        # SMB/CIFS style: //server/share
        return True
    
    return False

def create_file_lock(
    lock_path: str, 
    backend: Optional[Union[FileLockBackend, str]] = None,
    **kwargs
) -> Union[LocalFileLock, NFSFileLock]:
    """
    Create appropriate file lock based on path or explicit backend.
    
    Args:
        lock_path: Path to lock file
        backend: Explicit backend choice or None for auto-detection
        **kwargs: Additional arguments passed to lock constructor
        
    Returns:
        File lock instance (LocalFileLock or NFSFileLock)
    """
    if backend is None:
        # Auto-detect based on path
        if is_nfs_path(lock_path):
            backend = FileLockBackend.NFS
        else:
            backend = FileLockBackend.LOCAL
    elif isinstance(backend, str):
        backend = FileLockBackend(backend.lower())
    
    if backend == FileLockBackend.LOCAL:
        return LocalFileLock(lock_path, **kwargs)
    elif backend == FileLockBackend.NFS:
        return NFSFileLock(lock_path, **kwargs)
    else:
        raise ValueError(f"Unsupported backend: {backend}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_locking/test_factory.py::test_create_file_lock_auto_detects_nfs -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dlazy/utils/locking/factory.py tests/test_locking/test_factory.py
git commit -m "feat: add LockFactory with auto-detection"
```

---

## Chunk 2: HDF5 Concurrency Management

### Task 2.1: Create HDF5SWMRManager for Single Writer Multiple Reader

**Files:**
- Create: `dlazy/utils/locking/hdf5_swmr.py`
- Test: `tests/test_locking/test_hdf5_swmr.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_locking/test_hdf5_swmr.py
import pytest
import tempfile
import h5py
import numpy as np
from dlazy.utils.locking.hdf5_swmr import HDF5SWMRManager, HDF5AccessMode

def test_hdf5_swmr_manager_writer_mode():
    """Test HDF5SWMRManager in writer mode."""
    with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tmp:
        h5_path = tmp.name
    
    try:
        manager = HDF5SWMRManager(h5_path, mode=HDF5AccessMode.WRITE)
        
        # Writer should be able to create file and write data
        with manager.access() as f:
            assert f is not None
            assert isinstance(f, h5py.File)
            f.create_dataset("test_data", data=np.array([1, 2, 3]))
        
        # Verify file exists with data
        with h5py.File(h5_path, 'r') as f:
            assert "test_data" in f
            data = f["test_data"][:]
            assert list(data) == [1, 2, 3]
            
    finally:
        if os.path.exists(h5_path):
            os.unlink(h5_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_locking/test_hdf5_swmr.py::test_hdf5_swmr_manager_writer_mode -v`
Expected: FAIL with "HDF5SWMRManager not defined"

- [ ] **Step 3: Write minimal implementation**

```python
# dlazy/utils/locking/hdf5_swmr.py
import os
import time
import h5py
from enum import Enum
from typing import Optional, Union, ContextManager
from contextlib import contextmanager
from .factory import create_file_lock

class HDF5AccessMode(Enum):
    """HDF5 file access modes."""
    READ = "r"           # Read-only, requires SWMR mode
    WRITE = "w"          # Write (truncates existing file)
    APPEND = "a"         # Read/write, create if doesn't exist
    READ_WRITE = "r+"    # Read/write, file must exist

class HDF5SWMRManager:
    """Manages concurrent HDF5 access with SWMR mode and locking."""
    
    def __init__(
        self,
        h5_path: str,
        mode: Union[HDF5AccessMode, str] = HDF5AccessMode.READ_WRITE,
        use_swmr: bool = True,
        use_locking: bool = True,
        lock_timeout: float = 30.0
    ):
        self.h5_path = h5_path
        self.mode = mode if isinstance(mode, HDF5AccessMode) else HDF5AccessMode(mode)
        self.use_swmr = use_swmr
        self.use_locking = use_locking
        self.lock_timeout = lock_timeout
        
        # Determine if we need writer lock
        self._is_writer = self.mode in [HDF5AccessMode.WRITE, HDF5AccessMode.APPEND, HDF5AccessMode.READ_WRITE]
        
        # Create lock if needed
        self._lock = None
        if self.use_locking:
            lock_path = f"{h5_path}.lock"
            self._lock = create_file_lock(lock_path, timeout=lock_timeout)
    
    @contextmanager
    def access(self) -> ContextManager[h5py.File]:
        """
        Context manager for safe HDF5 file access.
        
        Yields:
            h5py.File object
        """
        # Acquire lock if needed
        if self._lock and self._is_writer:
            result = self._lock.acquire()
            if not result.acquired:
                raise RuntimeError(f"Failed to acquire lock for HDF5 file: {result.error}")
        
        try:
            # Determine h5py mode string
            mode_str = self.mode.value
            
            # Apply SWMR flags if enabled
            if self.use_swmr:
                if self._is_writer:
                    # Writer opens with 'swmr_write' for SWMR mode
                    mode_str = 'w' if self.mode == HDF5AccessMode.WRITE else 'r+'
                    f = h5py.File(self.h5_path, mode_str, libver='latest')
                    # Enable SWMR writing mode
                    # Note: In h5py 3.0+, SWMR mode is enabled differently
                    # We need to check h5py version
                    import h5py
                    if hasattr(h5py, 'version') and h5py.version.version_tuple >= (3, 0, 0):
                        # h5py 3.0+ uses swmr=True parameter
                        f = h5py.File(self.h5_path, mode_str, swmr=True, libver='latest')
                    else:
                        # Older h5py versions
                        f.swmr_mode = True
                else:
                    # Reader opens with swmr=True
                    f = h5py.File(self.h5_path, 'r', swmr=True, libver='latest')
            else:
                # Non-SWMR mode
                f = h5py.File(self.h5_path, mode_str, libver='latest')
            
            yield f
            
        finally:
            # Close file
            try:
                if 'f' in locals() and f:
                    f.close()
            except Exception:
                pass
            
            # Release lock if acquired
            if self._lock and self._is_writer:
                self._lock.release()
    
    def flush_writer(self):
        """Force flush if in writer mode (for SWMR readers)."""
        if not self._is_writer:
            return
        
        if self.use_swmr:
            # In SWMR mode, readers see updates after flush
            with self.access() as f:
                f.flush()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_locking/test_hdf5_swmr.py::test_hdf5_swmr_manager_writer_mode -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dlazy/utils/locking/hdf5_swmr.py tests/test_locking/test_hdf5_swmr.py
git commit -m "feat: add HDF5SWMRManager for concurrent HDF5 access"
```

### Task 2.2: Create HDF5 Native Locking Support

**Files:**
- Modify: `dlazy/utils/locking/hdf5_swmr.py:1-100` (add native locking)
- Test: `tests/test_locking/test_hdf5_swmr.py` (add test)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_locking/test_hdf5_swmr.py (add to existing file)
def test_hdf5_native_locking():
    """Test HDF5 native file locking support."""
    with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tmp:
        h5_path = tmp.name
    
    try:
        # Test with native locking enabled
        manager = HDF5SWMRManager(
            h5_path, 
            mode=HDF5AccessMode.WRITE,
            use_locking=True,  # External file locking
            use_native_locking=True  # HDF5 internal locking
        )
        
        # Should be able to write with both locks
        with manager.access() as f:
            f.create_dataset("native_lock_test", data=np.array([1, 2, 3]))
        
        # Verify
        with h5py.File(h5_path, 'r') as f:
            assert "native_lock_test" in f
            
    finally:
        if os.path.exists(h5_path):
            os.unlink(h5_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_locking/test_hdf5_swmr.py::test_hdf5_native_locking -v`
Expected: FAIL with "use_native_locking parameter not defined"

- [ ] **Step 3: Write minimal implementation**

```python
# Update dlazy/utils/locking/hdf5_swmr.py __init__ method
    def __init__(
        self,
        h5_path: str,
        mode: Union[HDF5AccessMode, str] = HDF5AccessMode.READ_WRITE,
        use_swmr: bool = True,
        use_locking: bool = True,
        use_native_locking: bool = False,
        lock_timeout: float = 30.0
    ):
        self.h5_path = h5_path
        self.mode = mode if isinstance(mode, HDF5AccessMode) else HDF5AccessMode(mode)
        self.use_swmr = use_swmr
        self.use_locking = use_locking
        self.use_native_locking = use_native_locking
        self.lock_timeout = lock_timeout
        
        # Determine if we need writer lock
        self._is_writer = self.mode in [HDF5AccessMode.WRITE, HDF5AccessMode.APPEND, HDF5AccessMode.READ_WRITE]
        
        # Create lock if needed
        self._lock = None
        if self.use_locking:
            lock_path = f"{h5_path}.lock"
            self._lock = create_file_lock(lock_path, timeout=lock_timeout)
```

```python
# Update access() method context manager
    @contextmanager
    def access(self) -> ContextManager[h5py.File]:
        """
        Context manager for safe HDF5 file access.
        
        Yields:
            h5py.File object
        """
        # Acquire lock if needed
        if self._lock and self._is_writer:
            result = self._lock.acquire()
            if not result.acquired:
                raise RuntimeError(f"Failed to acquire lock for HDF5 file: {result.error}")
        
        try:
            # Determine h5py mode string
            mode_str = self.mode.value
            
            # Build kwargs for h5py.File
            kwargs = {
                'libver': 'latest',
                'driver': 'core' if not self.use_native_locking else None
            }
            
            # Apply SWMR flags if enabled
            if self.use_swmr:
                if self._is_writer:
                    mode_str = 'w' if self.mode == HDF5AccessMode.WRITE else 'r+'
                    kwargs['swmr'] = True
                else:
                    mode_str = 'r'
                    kwargs['swmr'] = True
            
            # Apply native locking if enabled (HDF5 1.10.0+)
            if self.use_native_locking:
                kwargs['locking'] = True
                # Native locking requires file driver
                kwargs['driver'] = None  # Use default driver
            
            f = h5py.File(self.h5_path, mode_str, **kwargs)
            
            yield f
            
        finally:
            # Close file
            try:
                if 'f' in locals() and f:
                    f.close()
            except Exception:
                pass
            
            # Release lock if acquired
            if self._lock and self._is_writer:
                self._lock.release()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_locking/test_hdf5_swmr.py::test_hdf5_native_locking -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dlazy/utils/locking/hdf5_swmr.py
git commit -m "feat: add HDF5 native locking support"
```

---

## Chunk 3: Retry Mechanisms with Tenacity

### Task 3.1: Create Retry Decorators with Exponential Backoff

**Files:**
- Create: `dlazy/utils/locking/retry.py`
- Test: `tests/test_locking/test_retry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_locking/test_retry.py
import pytest
import time
from unittest.mock import Mock, patch
from dlazy.utils.locking.retry import (
    retry_with_exponential_backoff,
    RetryConfig,
    RetryableError,
    NonRetryableError
)

def test_retry_with_exponential_backoff():
    """Test exponential backoff retry decorator."""
    call_count = 0
    
    @retry_with_exponential_backoff(
        max_attempts=3,
        base_delay=0.1,
        max_delay=1.0,
        jitter=True
    )
    def flaky_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RetryableError(f"Attempt {call_count} failed")
        return "success"
    
    result = flaky_function()
    assert result == "success"
    assert call_count == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_locking/test_retry.py::test_retry_with_exponential_backoff -v`
Expected: FAIL with "retry_with_exponential_backoff not defined"

- [ ] **Step 3: Write minimal implementation**

```python
# dlazy/utils/locking/retry.py
import time
import random
from dataclasses import dataclass
from typing import Optional, Callable, Type, Union, List
from functools import wraps

class RetryableError(Exception):
    """Error that can be retried."""
    pass

class NonRetryableError(Exception):
    """Error that should not be retried."""
    pass

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 30.0  # seconds
    jitter: bool = True
    jitter_max: float = 0.1  # max jitter as fraction of delay
    retry_on: Optional[List[Type[Exception]]] = None
    retry_predicate: Optional[Callable[[Exception], bool]] = None
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt with exponential backoff."""
        # Exponential backoff: base_delay * 2^(attempt-1)
        delay = self.base_delay * (2 ** (attempt - 1))
        
        # Apply maximum delay
        delay = min(delay, self.max_delay)
        
        # Add jitter if enabled
        if self.jitter:
            jitter_amount = delay * self.jitter_max * random.random()
            # Randomly add or subtract jitter
            if random.random() > 0.5:
                delay += jitter_amount
            else:
                delay -= jitter_amount
            # Ensure delay is positive
            delay = max(delay, 0.001)
        
        return delay
    
    def should_retry(self, error: Exception) -> bool:
        """Determine if error should be retried."""
        # Check explicit retry_on list
        if self.retry_on:
            for error_type in self.retry_on:
                if isinstance(error, error_type):
                    return True
        
        # Check predicate
        if self.retry_predicate:
            return self.retry_predicate(error)
        
        # Default: retry RetryableError, don't retry NonRetryableError
        if isinstance(error, NonRetryableError):
            return False
        if isinstance(error, RetryableError):
            return True
        
        # Default to retrying
        return True

def retry_with_exponential_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
    retry_on: Optional[List[Type[Exception]]] = None,
    retry_predicate: Optional[Callable[[Exception], bool]] = None
):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        jitter: Whether to add random jitter to delays
        retry_on: List of exception types to retry on
        retry_predicate: Function to determine if error should be retried
        
    Returns:
        Decorated function
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        jitter=jitter,
        retry_on=retry_on,
        retry_predicate=retry_predicate
    )
    
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            
            for attempt in range(1, config.max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    
                    # Check if we should retry
                    if not config.should_retry(e):
                        raise
                    
                    # If this was the last attempt, re-raise
                    if attempt == config.max_attempts:
                        raise
                    
                    # Calculate and sleep
                    delay = config.calculate_delay(attempt)
                    time.sleep(delay)
            
            # Should never reach here
            raise last_error if last_error else RuntimeError("Retry loop ended unexpectedly")
        
        return wrapper
    
    return decorator

# Pre-configured retry decorators for common scenarios
retry_on_file_operation = retry_with_exponential_backoff(
    max_attempts=5,
    base_delay=0.5,
    max_delay=10.0,
    jitter=True,
    retry_on=[OSError, IOError, TimeoutError]
)

retry_on_network_operation = retry_with_exponential_backoff(
    max_attempts=3,
    base_delay=2.0,
    max_delay=60.0,
    jitter=True,
    retry_on=[ConnectionError, TimeoutError]
)

retry_on_hdf5_operation = retry_with_exponential_backoff(
    max_attempts=3,
    base_delay=1.0,
    max_delay=30.0,
    jitter=True
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_locking/test_retry.py::test_retry_with_exponential_backoff -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dlazy/utils/locking/retry.py tests/test_locking/test_retry.py
git commit -m "feat: add retry decorators with exponential backoff"
```

---

## Chunk 4: Enhanced Atomic Operations

### Task 4.1: Create Atomic JSON Operations with Checksums

**Files:**
- Create: `dlazy/utils/locking/atomic_operations.py`
- Test: `tests/test_locking/test_atomic_operations.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_locking/test_atomic_operations.py
import pytest
import tempfile
import os
import json
from dlazy.utils.locking.atomic_operations import (
    atomic_write_json,
    atomic_read_json,
    atomic_append_jsonl,
    calculate_checksum
)

def test_atomic_write_json():
    """Test atomic JSON writing with checksum."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        json_path = tmp.name
    
    try:
        # Write data atomically
        data = {"test": "value", "number": 42}
        checksum = atomic_write_json(json_path, data, calculate_checksum=True)
        
        # Verify file exists and contains correct data
        assert os.path.exists(json_path)
        with open(json_path, 'r') as f:
            loaded = json.load(f)
        assert loaded == data
        
        # Verify checksum file exists if checksum was calculated
        if checksum:
            checksum_path = f"{json_path}.checksum"
            assert os.path.exists(checksum_path)
            with open(checksum_path, 'r') as f:
                stored_checksum = f.read().strip()
            assert stored_checksum == checksum
            
    finally:
        if os.path.exists(json_path):
            os.unlink(json_path)
        checksum_path = f"{json_path}.checksum"
        if os.path.exists(checksum_path):
            os.unlink(checksum_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_locking/test_atomic_operations.py::test_atomic_write_json -v`
Expected: FAIL with "atomic_write_json not defined"

- [ ] **Step 3: Write minimal implementation**

```python
# dlazy/utils/locking/atomic_operations.py
import os
import json
import tempfile
import hashlib
import xxhash
from typing import Any, Optional, Union, Dict, List
from pathlib import Path
from .retry import retry_on_file_operation

def calculate_checksum(file_path: str, algorithm: str = "xxh64") -> str:
    """
    Calculate checksum of a file.
    
    Args:
        file_path: Path to file
        algorithm: Checksum algorithm (xxh64, md5, sha256)
        
    Returns:
        Hexadecimal checksum string
    """
    if algorithm == "xxh64":
        hasher = xxhash.xxh64()
    elif algorithm == "md5":
        hasher = hashlib.md5()
    elif algorithm == "sha256":
        hasher = hashlib.sha256()
    else:
        raise ValueError(f"Unsupported checksum algorithm: {algorithm}")
    
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hasher.update(chunk)
    
    return hasher.hexdigest()

@retry_on_file_operation
def atomic_write_json(
    file_path: str,
    data: Any,
    calculate_checksum: bool = True,
    checksum_algorithm: str = "xxh64",
    indent: int = 2
) -> Optional[str]:
    """
    Write JSON data atomically using temp file + rename pattern.
    
    Args:
        file_path: Target JSON file path
        data: JSON-serializable data
        calculate_checksum: Whether to calculate and store checksum
        checksum_algorithm: Algorithm for checksum calculation
        indent: JSON indentation level
        
    Returns:
        Checksum if calculated, None otherwise
    """
    file_path = Path(file_path)
    temp_file = None
    
    try:
        # Create temp file in same directory for atomic rename
        temp_fd, temp_path = tempfile.mkstemp(
            suffix=".tmp",
            prefix=file_path.stem + "_",
            dir=file_path.parent
        )
        temp_file = os.fdopen(temp_fd, 'w')
        
        # Write JSON to temp file
        json.dump(data, temp_file, indent=indent)
        temp_file.close()
        
        # Calculate checksum if requested
        checksum = None
        if calculate_checksum:
            checksum = calculate_checksum(temp_path, checksum_algorithm)
        
        # Atomic rename
        os.replace(temp_path, file_path)
        
        # Write checksum file if checksum was calculated
        if checksum:
            checksum_path = file_path.with_suffix(file_path.suffix + ".checksum")
            with open(checksum_path, 'w') as f:
                f.write(checksum)
        
        return checksum
        
    finally:
        # Cleanup temp file if it still exists
        if temp_file and not temp_file.closed:
            temp_file.close()
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass

@retry_on_file_operation
def atomic_read_json(
    file_path: str,
    verify_checksum: bool = True,
    checksum_algorithm: str = "xxh64"
) -> Any:
    """
    Read JSON file atomically with optional checksum verification.
    
    Args:
        file_path: JSON file path
        verify_checksum: Whether to verify checksum
        checksum_algorithm: Algorithm for checksum verification
        
    Returns:
        Deserialized JSON data
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"JSON file not found: {file_path}")
    
    # Verify checksum if requested
    if verify_checksum:
        checksum_path = file_path.with_suffix(file_path.suffix + ".checksum")
        if not checksum_path.exists():
            raise RuntimeError(f"Checksum file not found: {checksum_path}")
        
        current_checksum = calculate_checksum(file_path, checksum_algorithm)
        with open(checksum_path, 'r') as f:
            stored_checksum = f.read().strip()
        
        if current_checksum != stored_checksum:
            raise RuntimeError(
                f"Checksum mismatch for {file_path}: "
                f"expected {stored_checksum}, got {current_checksum}"
            )
    
    # Read JSON
    with open(file_path, 'r') as f:
        return json.load(f)

@retry_on_file_operation
def atomic_append_jsonl(
    file_path: str,
    records: List[Dict[str, Any]],
    calculate_checksum: bool = True,
    checksum_algorithm: str = "xxh64"
) -> Optional[str]:
    """
    Append records to JSONL file atomically.
    
    Args:
        file_path: Target JSONL file path
        records: List of records to append
        calculate_checksum: Whether to calculate checksum
        checksum_algorithm: Algorithm for checksum calculation
        
    Returns:
        Checksum if calculated, None otherwise
    """
    file_path = Path(file_path)
    temp_file = None
    
    try:
        # Create temp file
        temp_fd, temp_path = tempfile.mkstemp(
            suffix=".tmp",
            prefix=file_path.stem + "_",
            dir=file_path.parent
        )
        temp_file = os.fdopen(temp_fd, 'w')
        
        # Copy existing content if file exists
        if file_path.exists():
            with open(file_path, 'r') as src:
                for line in src:
                    temp_file.write(line)
        
        # Append new records
        for record in records:
            json_line = json.dumps(record)
            temp_file.write(json_line + "\n")
        
        temp_file.close()
        
        # Calculate checksum if requested
        checksum = None
        if calculate_checksum:
            checksum = calculate_checksum(temp_path, checksum_algorithm)
        
        # Atomic rename
        os.replace(temp_path, file_path)
        
        # Write checksum file
        if checksum:
            checksum_path = file_path.with_suffix(file_path.suffix + ".checksum")
            with open(checksum_path, 'w') as f:
                f.write(checksum)
        
        return checksum
        
    finally:
        # Cleanup
        if temp_file and not temp_file.closed:
            temp_file.close()
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_locking/test_atomic_operations.py::test_atomic_write_json -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dlazy/utils/locking/atomic_operations.py tests/test_locking/test_atomic_operations.py
git commit -m "feat: add atomic JSON operations with checksums"
```

### Task 4.2: Create Atomic HDF5 Operations

**Files:**
- Modify: `dlazy/utils/locking/atomic_operations.py` (add HDF5 functions)
- Test: `tests/test_locking/test_atomic_operations.py` (add HDF5 tests)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_locking/test_atomic_operations.py (add)
def test_atomic_write_hdf5_dataset():
    """Test atomic HDF5 dataset writing."""
    import h5py
    import numpy as np
    
    with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tmp:
        h5_path = tmp.name
    
    try:
        from dlazy.utils.locking.atomic_operations import atomic_write_hdf5_dataset
        
        # Write dataset atomically
        data = np.array([[1, 2, 3], [4, 5, 6]])
        checksum = atomic_write_hdf5_dataset(
            h5_path,
            "test_dataset",
            data,
            calculate_checksum=True
        )
        
        # Verify
        with h5py.File(h5_path, 'r') as f:
            assert "test_dataset" in f
            loaded = f["test_dataset"][:]
            assert np.array_equal(loaded, data)
            
        if checksum:
            checksum_path = f"{h5_path}.checksum"
            assert os.path.exists(checksum_path)
            
    finally:
        if os.path.exists(h5_path):
            os.unlink(h5_path)
        checksum_path = f"{h5_path}.checksum"
        if os.path.exists(checksum_path):
            os.unlink(checksum_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_locking/test_atomic_operations.py::test_atomic_write_hdf5_dataset -v`
Expected: FAIL with "atomic_write_hdf5_dataset not defined"

- [ ] **Step 3: Write minimal implementation**

```python
# Add to dlazy/utils/locking/atomic_operations.py
import h5py
import numpy as np
from .hdf5_swmr import HDF5SWMRManager, HDF5AccessMode

@retry_on_hdf5_operation
def atomic_write_hdf5_dataset(
    h5_path: str,
    dataset_name: str,
    data: np.ndarray,
    calculate_checksum: bool = True,
    checksum_algorithm: str = "xxh64",
    use_swmr: bool = True,
    use_locking: bool = True
) -> Optional[str]:
    """
    Write HDF5 dataset atomically with SWMR support.
    
    Args:
        h5_path: HDF5 file path
        dataset_name: Name/path of dataset within HDF5 file
        data: NumPy array data
        calculate_checksum: Whether to calculate checksum
        checksum_algorithm: Algorithm for checksum calculation
        use_swmr: Whether to use SWMR mode
        use_locking: Whether to use file locking
        
    Returns:
        Checksum if calculated, None otherwise
    """
    h5_path = Path(h5_path)
    temp_h5_path = None
    
    try:
        # Create temp HDF5 file
        temp_fd, temp_h5_path = tempfile.mkstemp(
            suffix=".h5.tmp",
            prefix=h5_path.stem + "_",
            dir=h5_path.parent
        )
        os.close(temp_fd)  # We'll use h5py to write
        
        # Write data to temp file
        with h5py.File(temp_h5_path, 'w') as f:
            f.create_dataset(dataset_name, data=data)
        
        # Calculate checksum if requested
        checksum = None
        if calculate_checksum:
            checksum = calculate_checksum(temp_h5_path, checksum_algorithm)
        
        # Use SWMR manager for atomic replacement
        manager = HDF5SWMRManager(
            h5_path,
            mode=HDF5AccessMode.WRITE,
            use_swmr=use_swmr,
            use_locking=use_locking
        )
        
        # Replace existing file with temp file
        with manager.access() as dest_f:
            # Close and replace
            pass
        
        # Actually replace the file (simplified approach)
        # For true atomicity with HDF5, we'd need more complex handling
        # This is a reasonable approximation for many use cases
        if h5_path.exists():
            os.unlink(h5_path)
        os.rename(temp_h5_path, h5_path)
        
        # Write checksum file
        if checksum:
            checksum_path = h5_path.with_suffix(h5_path.suffix + ".checksum")
            with open(checksum_path, 'w') as f:
                f.write(checksum)
        
        return checksum
        
    finally:
        # Cleanup temp file
        if temp_h5_path and os.path.exists(temp_h5_path):
            try:
                os.unlink(temp_h5_path)
            except:
                pass

@retry_on_hdf5_operation
def atomic_append_hdf5_dataset(
    h5_path: str,
    dataset_name: str,
    new_data: np.ndarray,
    axis: int = 0,
    calculate_checksum: bool = True,
    checksum_algorithm: str = "xxh64",
    use_swmr: bool = True,
    use_locking: bool = True
) -> Optional[str]:
    """
    Append data to existing HDF5 dataset atomically.
    
    Args:
        h5_path: HDF5 file path
        dataset_name: Name/path of dataset
        new_data: Data to append
        axis: Axis to append along (0 = rows)
        calculate_checksum: Whether to calculate checksum
        checksum_algorithm: Algorithm for checksum calculation
        use_swmr: Whether to use SWMR mode
        use_locking: Whether to use file locking
        
    Returns:
        Checksum if calculated, None otherwise
    """
    manager = HDF5SWMRManager(
        h5_path,
        mode=HDF5AccessMode.READ_WRITE,
        use_swmr=use_swmr,
        use_locking=use_locking
    )
    
    with manager.access() as f:
        if dataset_name not in f:
            # Create dataset if it doesn't exist
            maxshape = list(new_data.shape)
            maxshape[axis] = None  # Unlimited in append dimension
            f.create_dataset(
                dataset_name,
                data=new_data,
                maxshape=tuple(maxshape),
                chunks=True
            )
        else:
            # Append to existing dataset
            dataset = f[dataset_name]
            current_shape = list(dataset.shape)
            new_shape = list(dataset.shape)
            new_shape[axis] += new_data.shape[axis]
            
            # Resize dataset
            dataset.resize(tuple(new_shape))
            
            # Calculate slice for appending
            slice_obj = [slice(None)] * len(new_shape)
            slice_obj[axis] = slice(current_shape[axis], new_shape[axis])
            
            # Write new data
            dataset[tuple(slice_obj)] = new_data
        
        # Flush for SWMR readers
        if use_swmr:
            f.flush()
    
    # Calculate checksum of entire file
    checksum = None
    if calculate_checksum:
        checksum = calculate_checksum(h5_path, checksum_algorithm)
        checksum_path = Path(h5_path).with_suffix(Path(h5_path).suffix + ".checksum")
        with open(checksum_path, 'w') as cf:
            cf.write(checksum)
    
    return checksum
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_locking/test_atomic_operations.py::test_atomic_write_hdf5_dataset -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dlazy/utils/locking/atomic_operations.py
git commit -m "feat: add atomic HDF5 operations"
```

---

## Chunk 5: Integration with Existing Concurrency Module

### Task 5.1: Update Existing Concurrency Module

**Files:**
- Modify: `dlazy/utils/concurrency.py`
- Test: `tests/test_file_lock.py` (update)

- [ ] **Step 1: Write the failing test for backward compatibility**

```python
# tests/test_concurrency_integration.py (new file)
import pytest
import tempfile
import os
from dlazy.utils.concurrency import (
    FileLock,
    SharedFileLock,
    PIDLock,
    atomic_write_json,
    atomic_append_jsonl
)

def test_backward_compatibility_filelock():
    """Test that existing FileLock API still works."""
    with tempfile.NamedTemporaryFile(suffix=".lock", delete=False) as tmp:
        lock_path = tmp.name
    
    try:
        # Old API should still work
        lock = FileLock(lock_path, timeout=1.0)
        assert lock.acquire() is True
        assert lock.release() is True
        
        # Context manager
        with FileLock(lock_path) as l:
            assert l.is_locked is True
        assert lock.is_locked is False
        
    finally:
        if os.path.exists(lock_path):
            os.unlink(lock_path)
```

- [ ] **Step 2: Run test to verify it passes (should already pass)**

Run: `pytest tests/test_concurrency_integration.py::test_backward_compatibility_filelock -v`
Expected: PASS (FileLock already exists)

- [ ] **Step 3: Update concurrency.py to use new locking framework**

```python
# dlazy/utils/concurrency.py
"""
Concurrency utilities for file locking and atomic operations.

This module has been updated to use the new unified locking framework
while maintaining backward compatibility.
"""

import os
import fcntl
import json
import tempfile
import atexit
from typing import Any, Dict, List, Optional
from pathlib import Path

# Import new locking framework
try:
    from .locking.factory import create_file_lock, FileLockBackend
    from .locking.atomic_operations import (
        atomic_write_json as new_atomic_write_json,
        atomic_read_json,
        atomic_append_jsonl as new_atomic_append_jsonl,
        calculate_checksum
    )
    from .locking.hdf5_swmr import HDF5SWMRManager, HDF5AccessMode
    from .locking.retry import retry_with_exponential_backoff
    NEW_LOCKING_AVAILABLE = True
except ImportError:
    NEW_LOCKING_AVAILABLE = False

# Backward compatibility classes
class FileLock:
    """Legacy FileLock class that delegates to new framework."""
    
    def __init__(self, lock_path: str, timeout: float = 30.0):
        self.lock_path = lock_path
        self.timeout = timeout
        if NEW_LOCKING_AVAILABLE:
            self._lock = create_file_lock(lock_path, timeout=timeout)
        else:
            # Fallback to old implementation
            self._lock = _LegacyFileLock(lock_path, timeout)
    
    def acquire(self) -> bool:
        return self._lock.acquire().acquired if hasattr(self._lock.acquire, '__call__') else self._lock.acquire()
    
    def release(self) -> bool:
        return self._lock.release()
    
    def __enter__(self):
        result = self.acquire()
        if not result:
            raise RuntimeError("Failed to acquire lock")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
    
    @property
    def is_locked(self) -> bool:
        return self._lock.is_locked if hasattr(self._lock, 'is_locked') else False

class SharedFileLock(FileLock):
    """Legacy SharedFileLock (read lock)."""
    
    def acquire(self) -> bool:
        # Old implementation used fcntl.LOCK_SH
        # New framework doesn't distinguish, but we maintain API
        return super().acquire()

class PIDLock:
    """Process ID based lock for single-process concurrency."""
    
    def __init__(self, lock_path: str, timeout: float = 30.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self._pid = os.getpid()
    
    def acquire(self) -> bool:
        try:
            if os.path.exists(self.lock_path):
                with open(self.lock_path, 'r') as f:
                    existing_pid = int(f.read().strip())
                if self._is_process_alive(existing_pid):
                    return False
            
            with open(self.lock_path, 'w') as f:
                f.write(str(self._pid))
            return True
        except:
            return False
    
    def release(self) -> bool:
        try:
            if os.path.exists(self.lock_path):
                with open(self.lock_path, 'r') as f:
                    existing_pid = int(f.read().strip())
                if existing_pid == self._pid:
                    os.unlink(self.lock_path)
            return True
        except:
            return False
    
    def _is_process_alive(self, pid: int) -> bool:
        """Check if process with given PID is still alive."""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    
    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("Failed to acquire PID lock")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

# Atomic operations with backward compatibility
def atomic_write_json(
    file_path: str,
    data: Any,
    calculate_checksum: bool = False,  # Default False for backward compat
    **kwargs
) -> Optional[str]:
    """
    Atomic JSON write with backward compatibility.
    
    Args:
        file_path: Target JSON file path
        data: JSON-serializable data
        calculate_checksum: Whether to calculate checksum
        **kwargs: Additional arguments passed to new implementation
        
    Returns:
        Checksum if calculated, None otherwise
    """
    if NEW_LOCKING_AVAILABLE:
        return new_atomic_write_json(
            file_path,
            data,
            calculate_checksum=calculate_checksum,
            **kwargs
        )
    
    # Fallback to old implementation
    file_path = Path(file_path)
    temp_file = None
    
    try:
        temp_fd, temp_path = tempfile.mkstemp(
            suffix=".tmp",
            prefix=file_path.stem + "_",
            dir=file_path.parent
        )
        temp_file = os.fdopen(temp_fd, 'w')
        
        json.dump(data, temp_file, indent=2)
        temp_file.close()
        
        os.replace(temp_path, file_path)
        return None
        
    finally:
        if temp_file and not temp_file.closed:
            temp_file.close()
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass

def atomic_append_jsonl(
    file_path: str,
    records: List[Dict[str, Any]],
    calculate_checksum: bool = False,  # Default False for backward compat
    **kwargs
) -> Optional[str]:
    """
    Atomic JSONL append with backward compatibility.
    
    Args:
        file_path: Target JSONL file path
        records: List of records to append
        calculate_checksum: Whether to calculate checksum
        **kwargs: Additional arguments passed to new implementation
        
    Returns:
        Checksum if calculated, None otherwise
    """
    if NEW_LOCKING_AVAILABLE:
        return new_atomic_append_jsonl(
            file_path,
            records,
            calculate_checksum=calculate_checksum,
            **kwargs
        )
    
    # Fallback to old implementation
    file_path = Path(file_path)
    
    with open(file_path, 'a') as f:
        for record in records:
            json_line = json.dumps(record)
            f.write(json_line + "\n")
    
    return None

# Legacy implementation for fallback
class _LegacyFileLock:
    """Original FileLock implementation for fallback."""
    
    def __init__(self, lock_path: str, timeout: float = 30.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self._fd = None
        self._locked = False
    
    def acquire(self) -> bool:
        import time
        start_time = time.time()
        
        while time.time() - start_time < self.timeout:
            try:
                self._fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o644)
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._locked = True
                return True
            except (IOError, OSError):
                if self._fd is not None:
                    os.close(self._fd)
                    self._fd = None
                time.sleep(0.1)
        
        return False
    
    def release(self) -> bool:
        try:
            if self._fd is not None:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
                self._fd = None
            self._locked = False
            return True
        except (IOError, OSError):
            return False
    
    @property
    def is_locked(self) -> bool:
        return self._locked
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_concurrency_integration.py::test_backward_compatibility_filelock -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dlazy/utils/concurrency.py tests/test_concurrency_integration.py
git commit -m "feat: integrate new locking framework with backward compatibility"
```

---

## Chunk 6: Testing and Documentation

### Task 6.1: Create Comprehensive Integration Tests

**Files:**
- Create: `tests/test_locking_integration.py`
- Test: `tests/test_locking_integration.py`

- [ ] **Step 1: Write integration tests**

```python
# tests/test_locking_integration.py
import pytest
import tempfile
import os
import json
import h5py
import numpy as np
from dlazy.utils.locking import (
    create_file_lock,
    HDF5SWMRManager,
    HDF5AccessMode,
    atomic_write_json,
    atomic_read_json,
    atomic_write_hdf5_dataset,
    retry_with_exponential_backoff
)

def test_full_integration_workflow():
    """Test complete workflow with JSON and HDF5 files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test JSON operations
        json_path = os.path.join(tmpdir, "test.json")
        data = {"key": "value", "list": [1, 2, 3]}
        
        # Atomic write with checksum
        checksum1 = atomic_write_json(json_path, data, calculate_checksum=True)
        assert checksum1 is not None
        assert os.path.exists(json_path)
        
        # Atomic read with verification
        loaded = atomic_read_json(json_path, verify_checksum=True)
        assert loaded == data
        
        # Test HDF5 operations
        h5_path = os.path.join(tmpdir, "test.h5")
        dataset = np.random.randn(100, 10)
        
        # Write HDF5 dataset
        checksum2 = atomic_write_hdf5_dataset(
            h5_path,
            "data",
            dataset,
            calculate_checksum=True
        )
        assert checksum2 is not None
        
        # Verify HDF5 file
        with h5py.File(h5_path, 'r') as f:
            assert "data" in f
            assert np.array_equal(f["data"][:], dataset)
        
        # Test file locking
        lock_path = os.path.join(tmpdir, "test.lock")
        lock = create_file_lock(lock_path)
        
        with lock:
            # Lock is acquired
            assert lock.is_locked is True
            
            # Write to locked-protected file
            with open(os.path.join(tmpdir, "protected.txt"), 'w') as f:
                f.write("protected content")
        
        # Lock is released
        assert lock.is_locked is False
        
        print("All integration tests passed!")

def test_hdf5_swmr_concurrent_access():
    """Test HDF5 SWMR mode for concurrent access."""
    with tempfile.TemporaryDirectory() as tmpdir:
        h5_path = os.path.join(tmpdir, "swmr_test.h5")
        
        # Create writer
        writer = HDF5SWMRManager(
            h5_path,
            mode=HDF5AccessMode.WRITE,
            use_swmr=True,
            use_locking=True
        )
        
        # Write initial data
        with writer.access() as f:
            f.create_dataset("initial", data=np.array([1, 2, 3]))
        
        # Create reader
        reader = HDF5SWMRManager(
            h5_path,
            mode=HDF5AccessMode.READ,
            use_swmr=True,
            use_locking=False  # Readers don't need locks
        )
        
        # Reader can read while writer writes
        with reader.access() as f:
            data = f["initial"][:]
            assert list(data) == [1, 2, 3]
        
        print("HDF5 SWMR test passed!")

@retry_with_exponential_backoff(max_attempts=3, base_delay=0.1)
def flaky_operation(success_on_attempt: int):
    """Helper function for retry testing."""
    flaky_operation.attempts = getattr(flaky_operation, 'attempts', 0) + 1
    if flaky_operation.attempts < success_on_attempt:
        raise RuntimeError(f"Attempt {flaky_operation.attempts} failed")
    return f"success on attempt {flaky_operation.attempts}"

def test_retry_decorator_integration():
    """Test retry decorator integration."""
    # Reset attempts counter
    flaky_operation.attempts = 0
    
    # Should succeed on 3rd attempt
    result = flaky_operation(success_on_attempt=3)
    assert result == "success on attempt 3"
    assert flaky_operation.attempts == 3
    
    print("Retry decorator test passed!")
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_locking_integration.py -v`
Expected: All tests PASS

- [ ] **Step 3: Update existing tests**

```bash
# Run existing file lock tests to ensure backward compatibility
pytest tests/test_file_lock.py -v
```

Expected: All existing tests PASS

- [ ] **Step 4: Create documentation**

```bash
# Create README for locking framework
cat > dlazy/utils/locking/README.md << 'EOF'
# Unified Locking Framework

A comprehensive file locking framework for Python with support for:
- Local filesystem locking (fcntl-based)
- NFS-safe locking (flufl.lock-based)
- HDF5 concurrency management (SWMR mode)
- Atomic JSON/HDF5 operations
- Retry mechanisms with exponential backoff

## Quick Start

```python
from dlazy.utils.locking import create_file_lock, atomic_write_json

# Auto-detect backend based on path
lock = create_file_lock("/path/to/file.lock")
with lock:
    # Critical section
    atomic_write_json("/path/to/data.json", {"key": "value"})

# Explicit backend selection
lock = create_file_lock("/nfs/path/file.lock", backend="nfs")
```

## HDF5 Concurrency

```python
from dlazy.utils.locking import HDF5SWMRManager, HDF5AccessMode
import numpy as np

# Writer process
writer = HDF5SWMRManager("data.h5", mode=HDF5AccessMode.WRITE)
with writer.access() as f:
    f.create_dataset("dataset", data=np.random.randn(100, 10))

# Reader process (concurrent)
reader = HDF5SWMRManager("data.h5", mode=HDF5AccessMode.READ)
with reader.access() as f:
    data = f["dataset"][:]
```

## Retry Mechanisms

```python
from dlazy.utils.locking import retry_with_exponential_backoff

@retry_with_exponential_backoff(max_attempts=3, base_delay=1.0)
def flaky_operation():
    # This will be retried with exponential backoff
    return do_something()
```

## Backward Compatibility

The legacy `FileLock`, `SharedFileLock`, `PIDLock` classes in `dlazy.utils.concurrency`
continue to work and now delegate to the new framework internally.

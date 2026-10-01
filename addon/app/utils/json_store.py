import json
import os
import tempfile
from pathlib import Path


def atomic_write_json(
    path,
    data,
    *,
    ensure_ascii=False,
    indent=2,
    sort_keys=False,
):
    """Write JSON atomically and durably in the target directory.

    The temporary file is created beside the destination so ``os.replace``
    remains atomic. The file is flushed and fsynced before replacement. The
    parent directory is then fsynced where supported so the rename itself is
    durable across a sudden power loss.
    """

    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.",
        suffix=".tmp",
        dir=target_path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(
            file_descriptor,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                data,
                file,
                ensure_ascii=ensure_ascii,
                indent=indent,
                sort_keys=sort_keys,
            )
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_path, target_path)
        _fsync_directory(target_path.parent)

    except Exception:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _fsync_directory(directory):
    # Windows cannot fsync a directory through os.open. On Linux (the HA
    # add-on host), failure to sync the rename is a failed durable save.
    if os.name != "posix":
        return
    flags = os.O_RDONLY

    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY

    directory_fd = os.open(directory, flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)

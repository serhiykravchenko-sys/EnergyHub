"""Read-only checks of one configured private address, never network discovery."""
import asyncio
from .endpoint import address


def helper_update(configured, proposed, previous):
    """Follow configuration while preserving an unapplied dashboard edit."""
    if configured and (proposed in (None, '', 'unknown', 'unavailable')
                       or proposed == previous and previous != configured):
        return configured
    return None


async def probe(value):
    try:
        ip = address(value)
    except (ValueError, TypeError):
        return 'unknown'
    process = None
    try:
        process = await asyncio.create_subprocess_exec('ping', '-c', '1', '-W', '2', ip,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        code = await asyncio.wait_for(process.wait(), timeout=4)
        # Exit 2 includes command/permission/unsupported-argument errors.
        return {0: 'reachable', 1: 'unreachable'}.get(code, 'unknown')
    except (OSError, asyncio.TimeoutError):
        return 'unknown'
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()

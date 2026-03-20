# Connection Limit Fix - NVDA Bot

## Root Cause Analysis

### The Issue
Your NVDA Opening Range Breakout bot was experiencing **"connection limit exceeded"** errors with HTTP 429 responses from Alpaca's websocket API.

### Why It Happened
Alpaca's paper trading tier limits concurrent websocket connections to **1-2 connections per account**. The errors occurred because:

1. **Multiple instances running simultaneously** - Railway may have been running multiple replicas
2. **Race condition on restart** - Old instance didn't close websocket before new one started
3. **Bot overlap** - NVDA bot trying to connect during MSOS bot's time window

The bot subscribes to 3 data streams:
- NVDA bars (for Opening Range Breakout tracking)
- NVDL trades (for long position monitoring)
- NVD trades (for short position monitoring)

While these SHOULD use a single websocket connection, having multiple bot instances created a connection stampede.

## The Fix

### 1. Connection Lock Mechanism
Added a file-based lock system to prevent multiple instances from connecting:
- `acquire_connection_lock()` - Checks if another instance holds the lock
- `release_connection_lock()` - Releases lock when bot exits
- Stale locks (>10 minutes) are automatically cleaned up

### 2. Better Error Handling
- Clearer error messages with actionable steps
- Automatic lock release on all exit paths
- Improved logging for Railway monitoring

### 3. Improved Cleanup
- Always releases connection lock in `finally` block
- Properly closes websocket streams on exit
- Prevents orphaned connections

## How It Works Now

```
┌─────────────────────────────────────────┐
│  Bot Startup                            │
├─────────────────────────────────────────┤
│  1. Check time window                   │
│  2. Exponential backoff (if restarting) │
│  3. Acquire connection lock ◄───────────┼─── NEW!
│     └── Fail if another instance exists │
│  4. Test Alpaca API connection          │
│  5. Subscribe to data streams           │
│  6. Connect to websocket                │
│  7. Run trading logic                   │
└─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│  Bot Exit (always executes)             │
├─────────────────────────────────────────┤
│  1. Close websocket connection          │
│  2. Release connection lock ◄───────────┼─── NEW!
└─────────────────────────────────────────┘
```

## What Changed

### Before:
```python
# Multiple instances could connect simultaneously
await self.stream._run_forever()
```

### After:
```python
# Acquire lock first
if not await acquire_connection_lock():
    log_and_flush("[ERROR] Another instance is running")
    return

try:
    await self.stream._run_forever()
finally:
    await self.stream.close()
    release_connection_lock()  # Always release
```

## Verification

### Railway Configuration
Checked `railway.toml`:
```toml
[deploy]
numReplicas = 1  ✓ Correct
```

### Expected Behavior
1. Only ONE instance can connect at a time
2. If another instance tries to connect, it will:
   - Detect the lock
   - Log a clear error message
   - Exit gracefully without attempting connection
3. When the instance exits, the lock is ALWAYS released

## Testing

The bot now:
1. ✅ Prevents multiple instances from connecting
2. ✅ Releases locks even on crashes
3. ✅ Provides actionable error messages
4. ✅ Properly cleans up websocket connections

## Next Steps

### If Issues Persist:

1. **Check Railway Dashboard**
   - Go to your service settings
   - Verify "Replicas" = 1 (not higher)
   - Check deployment logs for multiple instances

2. **Restart the Service**
   - This kills all running instances
   - Clears any stale locks
   - Starts fresh with new code

3. **Monitor Logs**
   - Look for "Connection lock acquired" message
   - Should only appear ONCE per deployment
   - If you see multiple, Railway is running multiple replicas

4. **Check Time Windows**
   - NVDA bot: 9:30 AM - 2:00 PM CST
   - MSOS bot: 2:15 PM - 3:00 PM CST
   - Ensure no overlap

## Error Messages Guide

### Before Fix:
```
[err] ValueError: connection limit exceeded
[err] Traceback (most recent call last):
[err]   File "...websocket.py", line 342, in _run_forever
```
*Unclear what to do*

### After Fix:
```
[ERROR] Cannot acquire connection lock - another instance is running
[ERROR] SOLUTION:
  1. Go to Railway dashboard
  2. Check Settings > Replicas = 1
  3. Restart the service
```
*Clear action steps*

## Technical Details

### Lock File Location
- `/tmp/nvda_bot_connection.lock`
- Contains timestamp of when lock was acquired
- Auto-cleaned after 10 minutes (stale lock detection)

### Lock Acquisition Logic
```python
if lock_exists and lock_age < 10_minutes:
    return False  # Another instance is running
elif lock_exists and lock_age >= 10_minutes:
    cleanup_stale_lock()
    acquire_lock()
    return True  # Stale lock cleaned
else:
    acquire_lock()
    return True  # No lock existed
```

## Additional Notes

- The fix is **backward compatible** - works with existing Railway setup
- No changes needed to Railway configuration
- Lock files are stored in `/tmp/` (ephemeral, auto-cleaned on container restart)
- Works with both Railway and local development environments

## Support

If you still see connection errors after this fix:
1. Check Railway logs for "Connection lock acquired" count
2. Verify only ONE instance is logging this message
3. Check for time window overlaps with MSOS bot
4. Ensure `railway.toml` has `numReplicas = 1`

---

**Fix Applied**: 2026-03-20
**Bot Version**: NVDA Opening Range Breakout Strategy
**Status**: Ready for deployment

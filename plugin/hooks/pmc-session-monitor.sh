#!/usr/bin/env bash
# PMC Session Monitor — auto-clear + resume when context hits 80%
#
# Runs as a background daemon (managed by supervisor).
# Watches /tmp/pmc-restart-needed written by the Stop hook.
# When found:
#   1. Reads tmux pane ID + session_id from signal file
#   2. Sends /clear to the Claude pane
#   3. Waits for Claude to reset
#   4. Sends a resume prompt — UserPromptSubmit will inject checkpoint context

set -e

SIGNAL_FILE="/tmp/pmc-restart-needed"
RESUME_MSG="[PMC AUTO-RESUME] Continua dalla sessione precedente — checkpoint caricato."
POLL_INTERVAL=5

log() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] pmc-session-monitor: $*" >&2
}

log "Started. Polling $SIGNAL_FILE every ${POLL_INTERVAL}s."

while true; do
    if [ -f "$SIGNAL_FILE" ]; then
        signal=$(cat "$SIGNAL_FILE")
        tmux_pane=$(echo "$signal" | cut -d'|' -f1)
        session_id=$(echo "$signal" | cut -d'|' -f2)

        log "Signal detected: pane=$tmux_pane session=$session_id"
        rm -f "$SIGNAL_FILE"

        # Verify tmux pane exists
        if [ -z "$tmux_pane" ] || ! tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qF "$tmux_pane"; then
            log "Pane $tmux_pane not found — trying to find Claude pane automatically"
            # Fallback: find pane running claude
            tmux_pane=$(tmux list-panes -a -F '#{pane_id} #{pane_current_command}' 2>/dev/null \
                | grep -i "claude\|node" | head -1 | awk '{print $1}')
        fi

        if [ -z "$tmux_pane" ]; then
            log "ERROR: could not find Claude tmux pane. Skipping restart."
            continue
        fi

        log "Sending /clear to pane $tmux_pane"

        # Send /clear command
        tmux send-keys -t "$tmux_pane" "" ""        # no-op to ensure pane is focused
        sleep 0.5
        tmux send-keys -t "$tmux_pane" "/clear" "Enter"
        sleep 3

        # Send resume message — UserPromptSubmit will inject checkpoint
        log "Sending resume prompt"
        tmux send-keys -t "$tmux_pane" "$RESUME_MSG" "Enter"

        log "Auto-clear+resume complete for session $session_id"
    fi

    sleep "$POLL_INTERVAL"
done

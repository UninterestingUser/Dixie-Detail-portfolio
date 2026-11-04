# Failure reporting for ops scripts. Source it.
#
# Under set -e a failed command ends a script without a word of its own, so
# a command that fails quietly (a pipeline that pipefail fails, a `$(...)`
# whose command died of a signal) leaves the last line of output looking
# like the step that broke. Found on 2026-11-03, when restore-test.sh
# stopped silently after "Restoring into ...".

# report_failures NAME
# From here on, a failed command that ends the script prints, before it
# exits, "NAME: FAIL: FILE line N: COMMAND exited with status S" to stderr,
# with each part's status when it was a pipeline. Turns on errtrace, so a
# failure inside a function is reported too. A failure inside `$(...)` is
# reported once, by the command that used it. Call it in the shell (or the
# subshell) that runs with set -e.
report_failures() {
	ops_failure_name=$1
	ops_failure_pid=$BASHPID
	set -o errtrace
	trap 'ops_report_failure "$?" "${PIPESTATUS[*]}" "${BASH_SOURCE[0]:-$0}" "$LINENO" "$BASH_COMMAND"' ERR
}

# ops_report_failure STATUS PIPESTATUS FILE LINE COMMAND: the ERR trap.
ops_report_failure() {
	# Inside $(...): the command that uses the output reports it.
	[[ $BASHPID == "$ops_failure_pid" ]] || return 0
	local command=$5 parts="" cut=""
	# For a function that failed, bash names the function's last command
	# (`return "$rc"`); the script's own line says what was called.
	if [[ $command == return* && -r $3 ]]; then
		command=$(sed -n "${4}s/^[[:space:]]*//p" "$3")
	fi
	[[ $2 != *" "* ]] || parts=" (pipeline parts: $2)"
	[[ " $1 $2 " != *" 141 "* ]] || cut="; 141 means a command was cut off (SIGPIPE): what it wrote to stopped reading"
	echo "$ops_failure_name: FAIL: ${3##*/} line $4: $command exited with status $1$parts$cut" >&2
}

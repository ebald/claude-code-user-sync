#!/bin/bash
# Finder double-click entry point. No synchronization is started by setup.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) || exit 1
/bin/bash "$script_dir/setup.sh" "$@"
result=$?
if ((result != 0)) && [[ -t 0 ]]; then
  printf '\nSetup did not finish. Review the message above.\nPress Enter to close. '
  read -r _
fi
exit "$result"

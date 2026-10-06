#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 claude_sync.py sync --live
result=$?
echo
if (( result == 0 )); then
  echo 'Synchronization complete. You can open Claude and sign in to the other account.'
else
  echo 'Synchronization did not complete. Check the message above.'
fi
read '?Press Enter to close.'
exit $result

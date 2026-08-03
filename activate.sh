#!/bin/sh
# Source this file to make the repository's command available in this shell.
if [ -n "${BASH_VERSION:-}" ]; then
  TODO_ACTIVATE_FILE=${BASH_SOURCE[0]}
elif [ -n "${ZSH_VERSION:-}" ]; then
  TODO_ACTIVATE_FILE=${(%):-%x}
else
  printf '%s\n' "activate.sh supports bash and zsh." >&2
  return 1
fi
TODO_ACTIVATE_ROOT=$(CDPATH= cd -- "$(dirname -- "$TODO_ACTIVATE_FILE")" && pwd)
case ":$PATH:" in
  *":$TODO_ACTIVATE_ROOT/bin:"*) ;;
  *) PATH="$TODO_ACTIVATE_ROOT/bin:$PATH" ;;
esac
export PATH
unset TODO_ACTIVATE_ROOT
unset TODO_ACTIVATE_FILE

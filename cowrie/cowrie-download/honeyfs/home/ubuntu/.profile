# ~/.profile: executed by the command interpreter for login shells.
if [ "$BASH" ]; then
  if [ -f ~/.bashrc ]; then
    . ~/.bashrc
  fi
fi
mesg n || true
export EDITOR=vim
export PATH=$PATH:$HOME/bin

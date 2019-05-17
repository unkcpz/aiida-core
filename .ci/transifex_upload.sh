#!/bin/bash

# Be verbose, and stop with error as soon there's one
set -ev

TRANSIFEX_USER="api"
pip install virtualenv
virtualenv ~/env
source ~/env/bin/activate
pip install transifex-client
pip install .[docs,testing]
cd docs
make gettext
sudo echo $'[https://www.transifex.com]\nhostname = https://www.transifex.com\nusername = '"$TRANSIFEX_USER"$'\npassword = '"$TRANSIFEX_PASSWORD"$'\ntoken = '"$TRANSIFEX_API_TOKEN"$'\n' > ~/.transifexrc
tx push -s

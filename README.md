# Slippi Daemon

## What is this?
A work-in-progress python script for listening and automatically connecting to Wiis running Slippi-Nintendont.
The reason I wanted this is for automatic replay capture on a given network, with the ability to run headless. 

This could have been accomplished using the official slippi-js library and node or something, but eh. 

In its current state, its _almost_ usable; there is a random bug I can't replicate easily that causes execution to stop,
(this is why there are a large amount of print statements in the code, yes I know I should use a debugger).

## Installation (kinda)
This is not ready for general usage (see the above bug/bad usability), but if you want to try it:
 - create a venv and install py-ubjson
```commandline
python3 -m venv venv
source venv/bin/activate
python3 -m pip install py-ubjson
```
 - edit main.py to point to your wii, or uncomment the first block to auto-listen for wiis
 - run
```commandline
python3 main.py
```

As an aside if anyone would help me with figuring out how to package this for easier use by an end user, please reach out!

## Future ideas/plans include:
 - Rebroadcasting to a random port that the official slippi launcher/other 3rd party programs can connect to
 - GUI interface for non-headless use-cases (maybe a webpage?)
 - Pulling defaults for connections from a config file
 - Automatic uploading of replay files elsewhere (scp, ftp, cloud?)
 - Other things I've forgotten at the moment
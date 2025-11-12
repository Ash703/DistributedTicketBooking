# Distributed Train Ticket Booking System

## Setup for Windows:
- Run setup.ps1
## Setup for Linux:
- Run setup.sh

Run compile_proto.ps1 / compile_proto.sh after each changes to proto file

## Server: 
### terminal 1
`python src/server/main.py 1`

### terminal 2
`python src/server/main.py 2`

### terminal 3
`python src/server/main.py 3`

## Client: 
`python src/client/command_line_main.py`

## Flask App:
`python web_app/app.py`

[Database Viewer](https://sqliteviewer.app/)

Note: Run `python -m src.server.database.connection` for initalization  if required.
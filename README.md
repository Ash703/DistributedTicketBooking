# Distributed Train Ticket Booking System

## Setup for Windows:
- Run setup.ps1
## Setup for Linux:
- Run setup.sh

Run compile_proto.ps1 / compile_proto.sh after each changes to proto file

Server: 
`python src/server/main.py`

Client: 
`python src/client/command_line_main.py`


[Database Viewer](https://sqliteviewer.app/)

Note: Run `python -m src.server.database.connection` for initalization  if required.
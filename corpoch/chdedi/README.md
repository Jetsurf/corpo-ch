# Corpo CH - Clone Hero Dedicated Server Manager
App to manage a set of CH Dedicated Servers

Global settings define redis config for all servers. Unsure if using django's DB ID here will cause issues.

Managed through `manage.py` with `run_ch_servers`

 - Open Configuration - Meant to be used when a server isn't configured for a tournament allowing all connections
 - Tournament Configuration - Specific settings to configure a server for a specific tournament.

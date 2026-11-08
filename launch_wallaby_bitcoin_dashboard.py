#!/usr/bin/env python3
"""Migration entry point for existing source installations."""
import sys
import launch_wallaby_wallet_server as server
if __name__=='__main__':server.main()
else:sys.modules[__name__]=server

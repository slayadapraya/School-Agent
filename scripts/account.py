#!/usr/bin/env python3
"""Create an account; generated login details are printed once."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.server import init,add_account
p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('--username');p.add_argument('--role',choices=['student','teacher','admin'],default='student');a=p.parse_args()
init();print(json.dumps(add_account(a.name,a.role,a.username),indent=2))

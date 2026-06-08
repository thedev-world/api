#!/usr/bin/env python3
"""Delete a developer from the database and update the planet JSON on S3.

Usage (from repo root)::

    PYTHONPATH=. python snippet/delete_github_user.py GITHUB_LOGIN
"""

from __future__ import annotations

import argparse
import asyncio
from sqlalchemy import delete, func, select
from app.database import AsyncSessionLocal
from app.models.developer import Developer
from app.workers.planet_task import update_planet_json

async def delete_user_from_db(github_login: str) -> bool:
    async with AsyncSessionLocal() as db:
        # Case-insensitive search
        stmt = select(Developer).where(func.lower(Developer.github_login) == github_login.lower())
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"User '{github_login}' not found in database.")
            return False
        
        login_found = user.github_login
        print(f"Deleting user '{login_found}' (ID: {user.id})...")

        await db.execute(delete(Developer).where(Developer.id == user.id))
        await db.commit()
        print(f"User '{login_found}' deleted from database.")
        return True

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("github_login", help="GitHub login of the user to delete")
    args = parser.parse_args()
    
    github_login = args.github_login.strip()
    if not github_login:
        print("Error: GitHub login cannot be empty.")
        return
    
    # 1. Delete from DB
    try:
        success = asyncio.run(delete_user_from_db(github_login))
    except Exception as e:
        print(f"Database error: {e}")
        return
    
    # 2. Trigger JSON update if deletion was successful
    if success:
        print("Triggering planet-data.json update to S3...")
        try:
            update_planet_json()
            print("S3 update completed successfully.")
        except Exception as e:
            print(f"Error updating JSON on S3: {e}")
            print("Note: The user was deleted from DB, but S3 might be out of sync.")
    else:
        print("Skipping S3 update because user was not found.")

if __name__ == "__main__":
    main()

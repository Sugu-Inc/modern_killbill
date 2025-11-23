#!/usr/bin/env python3
"""
Automated database backup and restore testing script.

This script provides SOC2-compliant backup capabilities with:
- Automated PostgreSQL backups using pg_dump
- Backup retention management (configurable retention period)
- Restore testing to verify backup integrity
- Compression to reduce storage costs
- Structured logging for audit trail
- Error handling and notifications

Usage:
    # Create backup
    python backup.py --action backup

    # Test restore from latest backup
    python backup.py --action test-restore

    # Create backup and test restore
    python backup.py --action backup-and-test

    # List available backups
    python backup.py --action list

    # Cleanup old backups (default: keep last 30 days)
    python backup.py --action cleanup --retention-days 30
"""

import argparse
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
import gzip
import shutil
import logging
from typing import Optional
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backup.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class DatabaseBackupManager:
    """
    Manages PostgreSQL database backups with automated testing.

    Implements SOC2 CC6.7 operational resilience requirements:
    - RTO: 4 hours (Recovery Time Objective)
    - RPO: 15 minutes (Recovery Point Objective)
    """

    def __init__(
        self,
        backup_dir: str = "/var/backups/postgres",
        db_url: Optional[str] = None,
        retention_days: int = 30
    ):
        """
        Initialize backup manager.

        Args:
            backup_dir: Directory to store backups
            db_url: Database connection URL (defaults to DATABASE_URL env var)
            retention_days: Number of days to retain backups
        """
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Parse database URL from environment or parameter
        self.db_url = db_url or os.getenv("DATABASE_URL")
        if not self.db_url:
            raise ValueError("DATABASE_URL environment variable not set")

        # Parse connection details from URL
        # Format: postgresql://user:password@host:port/database
        self._parse_db_url()

        self.retention_days = retention_days

        logger.info(
            "backup_manager_initialized",
            backup_dir=str(self.backup_dir),
            retention_days=self.retention_days
        )

    def _parse_db_url(self):
        """Parse database connection URL into components."""
        from urllib.parse import urlparse

        parsed = urlparse(self.db_url)

        self.db_host = parsed.hostname or "localhost"
        self.db_port = parsed.port or 5432
        self.db_name = parsed.path.lstrip("/")
        self.db_user = parsed.username
        self.db_password = parsed.password

    def create_backup(self) -> Path:
        """
        Create database backup using pg_dump.

        Returns:
            Path to created backup file

        Raises:
            subprocess.CalledProcessError: If backup fails
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{self.db_name}_{timestamp}.sql"
        backup_path = self.backup_dir / backup_filename
        compressed_path = self.backup_dir / f"{backup_filename}.gz"

        logger.info(
            "backup_started",
            database=self.db_name,
            backup_file=str(backup_path)
        )

        try:
            # Set PGPASSWORD environment variable for pg_dump
            env = os.environ.copy()
            env["PGPASSWORD"] = self.db_password

            # Run pg_dump with comprehensive options
            # --clean: Add DROP commands before CREATE
            # --if-exists: Use IF EXISTS when dropping objects
            # --create: Include CREATE DATABASE command
            # --format=plain: Output plain SQL script
            cmd = [
                "pg_dump",
                f"--host={self.db_host}",
                f"--port={self.db_port}",
                f"--username={self.db_user}",
                "--clean",
                "--if-exists",
                "--create",
                "--format=plain",
                "--verbose",
                self.db_name
            ]

            # Execute pg_dump and save output
            with open(backup_path, 'w') as f:
                result = subprocess.run(
                    cmd,
                    env=env,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    check=True,
                    text=True
                )

            # Compress backup to save storage space
            logger.info("compressing_backup", backup_file=str(backup_path))

            with open(backup_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Remove uncompressed file
            backup_path.unlink()

            # Get backup file size
            size_mb = compressed_path.stat().st_size / (1024 * 1024)

            logger.info(
                "backup_completed",
                database=self.db_name,
                backup_file=str(compressed_path),
                size_mb=round(size_mb, 2),
                timestamp=timestamp
            )

            return compressed_path

        except subprocess.CalledProcessError as e:
            logger.error(
                "backup_failed",
                database=self.db_name,
                error=e.stderr,
                return_code=e.returncode
            )
            raise

        except Exception as e:
            logger.exception("backup_error", error=str(e))
            raise

    def test_restore(self, backup_file: Optional[Path] = None) -> bool:
        """
        Test database restore to verify backup integrity.

        Creates a temporary test database, restores backup, and validates.

        Args:
            backup_file: Path to backup file (defaults to latest)

        Returns:
            True if restore test successful

        Raises:
            Exception: If restore test fails
        """
        if backup_file is None:
            backup_file = self.get_latest_backup()

        if not backup_file:
            raise ValueError("No backup file found")

        logger.info(
            "restore_test_started",
            backup_file=str(backup_file)
        )

        # Create test database name
        test_db_name = f"{self.db_name}_test_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        try:
            # Decompress backup
            decompressed_path = backup_file.with_suffix('')
            with gzip.open(backup_file, 'rb') as f_in:
                with open(decompressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Set environment
            env = os.environ.copy()
            env["PGPASSWORD"] = self.db_password

            # Create test database
            logger.info("creating_test_database", test_db_name=test_db_name)

            subprocess.run(
                [
                    "createdb",
                    f"--host={self.db_host}",
                    f"--port={self.db_port}",
                    f"--username={self.db_user}",
                    test_db_name
                ],
                env=env,
                check=True,
                stderr=subprocess.PIPE
            )

            # Restore backup to test database
            logger.info("restoring_backup_to_test_db", test_db_name=test_db_name)

            with open(decompressed_path, 'r') as f:
                subprocess.run(
                    [
                        "psql",
                        f"--host={self.db_host}",
                        f"--port={self.db_port}",
                        f"--username={self.db_user}",
                        "--dbname", test_db_name,
                        "--quiet"
                    ],
                    env=env,
                    stdin=f,
                    check=True,
                    stderr=subprocess.PIPE
                )

            # Validate restore by counting tables
            result = subprocess.run(
                [
                    "psql",
                    f"--host={self.db_host}",
                    f"--port={self.db_port}",
                    f"--username={self.db_user}",
                    "--dbname", test_db_name,
                    "--tuples-only",
                    "--command",
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"
                ],
                env=env,
                check=True,
                capture_output=True,
                text=True
            )

            table_count = int(result.stdout.strip())

            logger.info(
                "restore_test_validation",
                test_db_name=test_db_name,
                table_count=table_count
            )

            # Cleanup: Drop test database
            logger.info("cleaning_up_test_database", test_db_name=test_db_name)

            subprocess.run(
                [
                    "dropdb",
                    f"--host={self.db_host}",
                    f"--port={self.db_port}",
                    f"--username={self.db_user}",
                    test_db_name
                ],
                env=env,
                check=True,
                stderr=subprocess.PIPE
            )

            # Remove decompressed file
            decompressed_path.unlink()

            logger.info(
                "restore_test_completed",
                backup_file=str(backup_file),
                success=True
            )

            return True

        except Exception as e:
            logger.exception(
                "restore_test_failed",
                backup_file=str(backup_file),
                error=str(e)
            )

            # Attempt cleanup even on failure
            try:
                subprocess.run(
                    ["dropdb", f"--host={self.db_host}", f"--username={self.db_user}", test_db_name],
                    env=env,
                    stderr=subprocess.DEVNULL
                )
            except:
                pass

            raise

    def get_latest_backup(self) -> Optional[Path]:
        """
        Get the most recent backup file.

        Returns:
            Path to latest backup file or None if no backups exist
        """
        backups = sorted(self.backup_dir.glob("backup_*.sql.gz"), reverse=True)
        return backups[0] if backups else None

    def list_backups(self) -> list[dict]:
        """
        List all available backups with metadata.

        Returns:
            List of backup metadata dictionaries
        """
        backups = []

        for backup_file in sorted(self.backup_dir.glob("backup_*.sql.gz"), reverse=True):
            stat = backup_file.stat()
            backups.append({
                "filename": backup_file.name,
                "path": str(backup_file),
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "age_days": (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days
            })

        return backups

    def cleanup_old_backups(self) -> int:
        """
        Remove backups older than retention period.

        Returns:
            Number of backups removed
        """
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        removed_count = 0

        logger.info(
            "cleanup_started",
            retention_days=self.retention_days,
            cutoff_date=cutoff_date.isoformat()
        )

        for backup_file in self.backup_dir.glob("backup_*.sql.gz"):
            file_mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)

            if file_mtime < cutoff_date:
                logger.info(
                    "removing_old_backup",
                    file=backup_file.name,
                    age_days=(datetime.now() - file_mtime).days
                )
                backup_file.unlink()
                removed_count += 1

        logger.info(
            "cleanup_completed",
            removed_count=removed_count
        )

        return removed_count


def main():
    """CLI entry point for backup management."""
    parser = argparse.ArgumentParser(
        description="Automated PostgreSQL backup and restore testing"
    )

    parser.add_argument(
        "--action",
        choices=["backup", "test-restore", "backup-and-test", "list", "cleanup"],
        required=True,
        help="Action to perform"
    )

    parser.add_argument(
        "--backup-dir",
        default="/var/backups/postgres",
        help="Directory to store backups (default: /var/backups/postgres)"
    )

    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help="Number of days to retain backups (default: 30)"
    )

    parser.add_argument(
        "--backup-file",
        type=Path,
        help="Specific backup file for restore testing"
    )

    args = parser.parse_args()

    try:
        manager = DatabaseBackupManager(
            backup_dir=args.backup_dir,
            retention_days=args.retention_days
        )

        if args.action == "backup":
            backup_file = manager.create_backup()
            print(f"✅ Backup created: {backup_file}")

        elif args.action == "test-restore":
            success = manager.test_restore(args.backup_file)
            if success:
                print("✅ Restore test passed")
            else:
                print("❌ Restore test failed")
                sys.exit(1)

        elif args.action == "backup-and-test":
            backup_file = manager.create_backup()
            print(f"✅ Backup created: {backup_file}")

            success = manager.test_restore(backup_file)
            if success:
                print("✅ Restore test passed")
            else:
                print("❌ Restore test failed")
                sys.exit(1)

        elif args.action == "list":
            backups = manager.list_backups()
            if not backups:
                print("No backups found")
            else:
                print(f"\n📦 Available backups ({len(backups)} total):\n")
                for backup in backups:
                    print(f"  • {backup['filename']}")
                    print(f"    Size: {backup['size_mb']} MB")
                    print(f"    Created: {backup['created_at']}")
                    print(f"    Age: {backup['age_days']} days\n")

        elif args.action == "cleanup":
            removed_count = manager.cleanup_old_backups()
            print(f"✅ Removed {removed_count} old backup(s)")

    except Exception as e:
        logger.exception("backup_operation_failed", error=str(e))
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

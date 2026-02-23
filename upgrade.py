"""
Upgrade script for Open-LLM-VTuber.

This script handles pulling updates, managing submodules, and syncing configurations.
"""

import time
from upgrade_codes.upgrade_manager import UpgradeManager
from upgrade_codes.upgrade_core.constants import TEXTS

upgrade_manager = UpgradeManager()
upgrade_manager.check_user_config_exists()


def _check_prerequisites(texts: dict) -> bool:
    """Check git installation and repository status."""
    logger = upgrade_manager.logger

    if not upgrade_manager.check_git_installed():
        logger.error(texts["git_not_found"])
        return False

    response = input("\033[93m" + texts["operation_preview"] + "\033[0m").lower()
    if response != "y":
        return False

    success, error_msg = upgrade_manager.run_command(
        "git rev-parse --is-inside-work-tree"
    )
    if not success:
        logger.error(texts["not_git_repo"])
        logger.error(f"Error details: {error_msg}")
        return False

    return True


def _check_ahead_status(texts: dict) -> bool:
    """Check for unpushed commits (ahead of remote)."""
    logger = upgrade_manager.logger

    logger.info(texts["checking_ahead_status"])
    success, ahead_behind = upgrade_manager.run_command(
        "git rev-list --left-right --count HEAD...@{upstream}"
    )

    if not success:
        return True  # Proceed if we can't determine ahead/behind

    ahead, behind = map(int, ahead_behind.strip().split())
    if ahead > 0:
        logger.error(texts["local_ahead"].format(count=ahead))
        logger.error(texts["push_blocked"])
        logger.info(texts["backup_suggestion"])
        logger.warning(texts["abort_upgrade"])
        return False

    return True


def _stash_changes_if_needed(texts: dict) -> tuple[bool, bool]:
    """Stash uncommitted changes if present.

    Returns:
        Tuple of (success, has_changes)
    """
    logger = upgrade_manager.logger

    logger.info(texts["checking_stash"])
    success, changes = upgrade_manager.run_command("git status --porcelain")
    if not success:
        logger.error(f"Failed to check git status: {changes}")
        return False, False

    has_changes = bool(changes.strip())
    if not has_changes:
        return True, False

    change_count = len([line for line in changes.strip().split("\n") if line])
    logger.debug(texts["detected_changes"].format(count=change_count))
    logger.warning(texts["uncommitted"])

    operation, elapsed = upgrade_manager.time_operation(
        upgrade_manager.run_command, "git stash"
    )
    success, output = operation
    logger.debug(texts["operation_time"].format(operation="git stash", time=elapsed))

    if not success:
        logger.error(texts["stash_error"])
        logger.error(f"Error details: {output}")
        return False, False

    logger.info(texts["changes_stashed"])
    return True, True


def _fetch_and_pull(texts: dict, has_changes: bool) -> bool:
    """Fetch from remote and pull updates."""
    logger = upgrade_manager.logger

    # Check remote status
    logger.info(texts["checking_remote"])
    operation, elapsed = upgrade_manager.time_operation(
        upgrade_manager.run_command, "git fetch"
    )
    success, output = operation
    logger.debug(texts["operation_time"].format(operation="git fetch", time=elapsed))

    if success:
        success, ahead_behind = upgrade_manager.run_command(
            "git rev-list --left-right --count HEAD...@{upstream}"
        )
        if success:
            ahead, behind = ahead_behind.strip().split()
            if int(behind) > 0:
                logger.info(texts["remote_behind"].format(count=behind))
            else:
                logger.info(texts["remote_ahead"])

    # Pull updates
    logger.info(texts["pulling"])
    operation, elapsed = upgrade_manager.time_operation(
        upgrade_manager.run_command, "git pull"
    )
    success, output = operation
    logger.debug(texts["operation_time"].format(operation="git pull", time=elapsed))

    if not success:
        logger.error(texts["pull_error"])
        logger.error(f"Error details: {output}")
        if has_changes:
            _restore_stash(texts, force=True)
        return False

    return True


def _update_submodules(texts: dict) -> bool:
    """Update git submodules."""
    logger = upgrade_manager.logger

    submodules = upgrade_manager.get_submodule_list()
    if not submodules:
        logger.info(texts["no_submodules"])
        return True

    logger.info(texts["updating_submodules"])

    operation, elapsed = upgrade_manager.time_operation(
        upgrade_manager.run_command, "git submodule update --init --recursive"
    )
    success, output = operation
    logger.debug(
        texts["operation_time"].format(operation="git submodule update", time=elapsed)
    )

    if not success:
        logger.error(texts["submodule_update_error"])
        logger.error(f"Error details: {output}")
        return False

    for submodule in submodules:
        logger.debug(texts["submodule_updated"].format(submodule=submodule))

    return True


def _restore_stash(texts: dict, force: bool = False) -> bool:
    """Restore stashed changes.

    Args:
        texts: Localized text messages
        force: If True, restore even on conflict warnings

    Returns:
        True if successful, False otherwise
    """
    logger = upgrade_manager.logger

    logger.warning(texts["restoring"])
    operation, elapsed = upgrade_manager.time_operation(
        upgrade_manager.run_command, "git stash pop"
    )
    success, output = operation
    logger.debug(
        texts["operation_time"].format(operation="git stash pop", time=elapsed)
    )

    if not success:
        logger.error(texts["conflict_warning"])
        logger.error(f"Error details: {output}")
        logger.warning(texts["manual_resolve"])
        logger.info(texts["stash_list"])
        logger.info(texts["stash_pop"])
        return False

    return True


def run_upgrade():
    """Main upgrade workflow."""
    logger = upgrade_manager.logger
    start_time = time.time()

    lang = upgrade_manager.lang
    logger.info(TEXTS[lang]["welcome_message"])
    texts = TEXTS[lang]

    logger.info(texts["start_upgrade"])
    upgrade_manager.log_system_info()

    # Pre-checks
    if not _check_prerequisites(texts):
        return

    if not _check_ahead_status(texts):
        return

    # Stash local changes
    success, has_changes = _stash_changes_if_needed(texts)
    if not success:
        return

    # Pull updates
    if not _fetch_and_pull(texts, has_changes):
        return

    # Update submodules
    _update_submodules(texts)

    # Update config
    upgrade_manager.sync_user_config()
    upgrade_manager.update_user_config()

    # Restore stashed changes
    if has_changes:
        if not _restore_stash(texts):
            return

    # Completion summary
    end_time = time.time()
    total_elapsed = end_time - start_time
    logger.info(texts["finish_upgrade"].format(time=total_elapsed))

    logger.info(texts["upgrade_complete"])
    logger.info(texts["check_config"])
    logger.info(texts["resolve_conflicts"])
    logger.info(texts["check_backup"])


if __name__ == "__main__":
    run_upgrade()

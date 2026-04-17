from git import Repo
from src.constants import GIT_STASH_NAME, GIT_STASH_STATUSES

def is_git_repo(path):
    """Check if the given path is a Git repository."""
    try:
        _ = Repo(path, search_parent_directories=True).git_dir
        return True
    except Exception:
        return False

def get_current_branch(path):
    """Get the current branch name of the Git repository at the given path."""
    try:
        repo = Repo(path, search_parent_directories=True)
        return repo.active_branch.name
    except Exception:
        return None


def get_current_commit_hash(path):
    """Get the current commit ID of the Git repository at the given path."""
    try:
        repo = Repo(path, search_parent_directories=True)
        return repo.head.commit.hexsha
    except Exception:
        return None

def get_last_commit_remote_hash(path, remote_name="origin", branch_name="main"):
    """Get the last commit hash from the remote repository."""
    try:
        repo = Repo(path, search_parent_directories=True)
        remote = repo.remotes[remote_name]
        remote.fetch()
        remote_ref = f"{remote_name}/{branch_name}"
        return repo.refs[remote_ref].commit.hexsha
    except Exception:
        return None

def stash_changes(path):
    """Stash changes in the Git repository at the given path.

    Returns:
        str: 'stashed' if changes were stashed, 'nothing_to_stash' if repo is clean, 'failed' on error
    """
    try:
        repo = Repo(path, search_parent_directories=True)
        if repo.is_dirty(untracked_files=True):
            repo.git.stash("save", "-u", GIT_STASH_NAME)
            return GIT_STASH_STATUSES.STASHED
        return GIT_STASH_STATUSES.NOTHING_TO_STASH
    except Exception:
        return GIT_STASH_STATUSES.FAILED


def stash_pop_changes(path):
    """Pop the latest stash in the Git repository at the given path."""
    try:
        repo = Repo(path, search_parent_directories=True)
        # Use pop instead of apply to also remove from stash stack
        # Reference stash by its commit message
        repo.git.stash("pop", "--index", f"stash^{{/{GIT_STASH_NAME}}}")
        return True
    except Exception as e:
        # Fallback: try popping the most recent stash
        try:
            repo.git.stash("pop")
            return True
        except:
            return False


def checkout(path, target):
    """Checkout to the specified branch or commit ID in the Git repository at the given path."""
    try:
        repo = Repo(path, search_parent_directories=True)
        repo.git.checkout(target)
        return True
    except Exception:
        return False


def get_master_branch_name(path):
    """Get the name of the master branch in the Git repository at the given path."""
    try:
        repo = Repo(path, search_parent_directories=True)
        remote = repo.remotes["origin"]
        remote.fetch()
        for ref in remote.refs:
            if ref.remote_head in ["master", "main"]:
                return ref.remote_head
        return None
    except Exception:
        return None

def pull_changes(path, remote_name='origin', branch_name='main'):
    """Pull the latest changes from the remote repository."""
    try:
        repo = Repo(path, search_parent_directories=True)
        remote = repo.remotes[remote_name]
        remote.pull(branch_name)
        return True
    except Exception:
        return False


def get_remote_url(path, remote_name="origin"):
    """Get the URL of the specified remote in the Git repository at the given path."""
    try:
        repo = Repo(path, search_parent_directories=True)
        remote = repo.remotes[remote_name]
        return remote.url
    except Exception:
        return None


def is_target_a_commit(path, target):
    """Check if the target is a commit ID in the Git repository at the given path."""
    try:
        repo = Repo(path, search_parent_directories=True)
        repo.commit(target)
        return True
    except Exception:
        return False


def is_target_a_branch(path, target):
    """Check if the target is a branch name in the Git repository at the given path."""
    try:
        repo = Repo(path, search_parent_directories=True)
        repo.branches[target]
        return True
    except Exception:
        return False

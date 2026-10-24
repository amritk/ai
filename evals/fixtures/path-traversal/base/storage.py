"""Files users have uploaded, stored under one directory."""

import os


def save_upload(base_dir, filename, data):
    """Store `data` under `base_dir`, keeping only the final path component of `filename`."""
    name = os.path.basename(filename)
    if not name:
        raise ValueError("empty filename")
    path = os.path.join(base_dir, name)
    with open(path, "wb") as fh:
        fh.write(data)
    return path

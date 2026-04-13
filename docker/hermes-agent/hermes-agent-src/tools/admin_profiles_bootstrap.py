from pathlib import Path
import os

from gateway.platforms.api_server_admin_bootstrap import materialize_default_profile_if_present


if __name__ == "__main__":
    hermes_home = Path(os.getenv("HERMES_HOME", "/opt/data"))
    materialize_default_profile_if_present(hermes_home)

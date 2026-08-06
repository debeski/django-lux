import argparse
import sys

from . import __version__
from .scaffold import ScaffoldError, create_app, create_project, enable_agent, enable_updater


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="dlux",
        description="DjangoLux project and app scaffolding",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
        help="Print the installed DjangoLux version and exit.",
    )
    subparsers = parser.add_subparsers(dest="command")

    startproject_parser = subparsers.add_parser(
        "startproject",
        help="Create a new DjangoLux-ready Django project",
    )
    startproject_parser.add_argument("project_name")
    startproject_parser.add_argument("destination", nargs="?")
    startproject_parser.add_argument(
        "--image",
        help=(
            "Docker image the deployment pulls and the release workflow pushes, "
            "as name[:tag] (e.g. acme/billing:latest). Defaults to the project name, "
            "which exists in no registry — set this so update discovery works"
        ),
    )
    startproject_parser.add_argument(
        "--repo",
        help="GitHub repository as owner/name, used for the release URL",
    )
    startproject_parser.add_argument(
        "--no-input",
        action="store_true",
        help="Never prompt; use --image/--repo values or their defaults",
    )

    startapp_parser = subparsers.add_parser(
        "startapp",
        help="Create a new DjangoLux-native app in the current project",
    )
    startapp_parser.add_argument("app_name")
    startapp_parser.add_argument(
        "--register",
        action="store_true",
        help="Also register the new app in the current project settings and urls",
    )

    updater_parser = subparsers.add_parser(
        "enable-updater",
        help="Bootstrap verified inline updates in a generated Compose project",
    )
    updater_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the guarded changes (the default is a dry run)",
    )

    agent_parser = subparsers.add_parser(
        "enable-agent",
        help="Replace the resident composer-updater with composer-agent",
    )
    agent_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the guarded changes (the default is a dry run)",
    )
    agent_parser.add_argument("-f", "--file", help="Compose file relative to the project root")
    agent_parser.add_argument(
        "--allow-unverified-dlux",
        action="store_true",
        help="Forward Composer's explicit DjangoLux bridge-version override",
    )

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "startproject":
            project_root = create_project(
                project_name=args.project_name,
                destination=args.destination,
                image=args.image,
                repo=args.repo,
                interactive=False if args.no_input else None,
            )
            print(f"Created project scaffold at {project_root}")
        elif args.command == "startapp":
            app_root = create_app(
                app_name=args.app_name,
                register=args.register,
            )
            print(f"Created app scaffold at {app_root}")
        elif args.command == "enable-updater":
            result = enable_updater(apply=args.apply)
            mode = "Applied" if result["applied"] else "Dry run"
            files = ", ".join(result["files"]) if result["files"] else "no changes"
            print(f"{mode}: {files}")
            if result.get("backup_root"):
                print(f"Backups: {result['backup_root']}")
            print(f"Rebuild and redeploy once: {result['command']}")
        elif args.command == "enable-agent":
            print(
                "Deprecated: use './start.sh enable-agent' directly; "
                "this DjangoLux command forwards to Composer v1.2.0+.",
                file=sys.stderr,
            )
            result = enable_agent(
                apply=args.apply,
                compose_file=args.file or "",
                allow_unverified_dlux=args.allow_unverified_dlux,
            )
            mode = "Applied" if result["applied"] else "Dry run"
            files = ", ".join(result["files"]) if result["files"] else "no changes"
            print(f"{mode}: {files}")
            if result.get("backup_root"):
                print(f"Backups: {result['backup_root']}")
            if result.get("command"):
                print(f"Redeploy once: {result['command']}")
            else:
                print("Agent topology is already enabled.")
        return 0
    except ScaffoldError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

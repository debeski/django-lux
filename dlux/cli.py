import argparse
import sys

from .scaffold import ScaffoldError, create_app, create_project, enable_updater


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="dlux",
        description="DjangoLux project and app scaffolding",
    )
    subparsers = parser.add_subparsers(dest="command")

    startproject_parser = subparsers.add_parser(
        "startproject",
        help="Create a new DjangoLux-ready Django project",
    )
    startproject_parser.add_argument("project_name")
    startproject_parser.add_argument("destination", nargs="?")

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

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "startproject":
            project_root = create_project(
                project_name=args.project_name,
                destination=args.destination,
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
        return 0
    except ScaffoldError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

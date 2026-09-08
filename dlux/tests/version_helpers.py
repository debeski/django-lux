"""Version arithmetic for tests that need "a release newer than this one".

Several updater tests model a runtime volume holding a release above the baked
floor, and must not hardcode a literal that collides with the package version on
the next bump. They each did their own string surgery on the version, which
worked for exactly as long as every version was three integers: the first beta
turned `1.8.14b1` into `1.8.14b1.1`, which is not a version at all.

So the same rule the updater itself follows applies here — ask the parser.
"""

from packaging.version import Version


def newer_version(base):
    """The next FINAL release strictly above ``base``.

    Final, not the next prerelease, and deliberately: callers use this to stand
    in for "the release this deployment would be offered next", and a stable
    deployment is never offered a prerelease. Returning `1.8.14b2` here would
    make those tests fail against the channel guard for a reason that has
    nothing to do with what they are testing.

    From a prerelease that means the release it precedes (`1.8.14b1` ->
    `1.8.14`); from a final it means the next patch (`1.8.14` -> `1.8.15`).
    """
    version = Version(str(base))
    major, minor, micro = (list(version.release) + [0, 0, 0])[:3]
    if version.is_prerelease:
        return f"{major}.{minor}.{micro}"
    return f"{major}.{minor}.{micro + 1}"

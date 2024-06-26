"""
Execute puppet routines
"""

import datetime
import logging
import os

import salt.utils.args
import salt.utils.files
import salt.utils.path
import salt.utils.platform
import salt.utils.stringutils
import salt.utils.yaml
from salt.exceptions import CommandExecutionError

log = logging.getLogger(__name__)


def __virtual__():
    """
    Only load if puppet is installed
    """
    unavailable_exes = ", ".join(
        exe for exe in ("facter", "puppet") if salt.utils.path.which(exe) is None
    )
    if unavailable_exes:
        return (
            False,
            "The puppet execution module cannot be loaded: {} unavailable.".format(
                unavailable_exes
            ),
        )
    else:
        return "puppet"


def _format_fact(output):
    try:
        fact, value = output.split(" => ", 1)
        value = value.strip()
    except ValueError:
        fact = None
        value = None
    return (fact, value)


class _Puppet:
    """
    Puppet helper class. Used to format command for execution.
    """

    def __init__(self):
        """
        Setup a puppet instance, based on the premis that default usage is to
        run 'puppet agent --test'. Configuration and run states are stored in
        the default locations.
        """
        self.subcmd = "agent"
        self.subcmd_args = []  # e.g. /a/b/manifest.pp

        self.kwargs = {"color": "false"}  # e.g. --tags=apache::server
        self.args = []  # e.g. --noop

        puppet_config = __salt__["cmd.run"](
            "puppet config print --render-as yaml vardir rundir confdir"
        )
        conf = salt.utils.yaml.safe_load(puppet_config)
        self.vardir = conf["vardir"]
        self.rundir = conf["rundir"]
        self.confdir = conf["confdir"]

        self.disabled_lockfile = self.vardir + "/state/agent_disabled.lock"
        self.run_lockfile = self.vardir + "/state/agent_catalog_run.lock"
        self.agent_pidfile = self.rundir + "/agent.pid"
        self.lastrunfile = self.vardir + "/state/last_run_summary.yaml"

    def __repr__(self):
        """
        Format the command string to executed using cmd.run_all.
        """
        cmd = "puppet {subcmd} --vardir {vardir} --confdir {confdir}".format(
            **self.__dict__
        )

        args = " ".join(self.subcmd_args)
        args += "".join([f" --{k}" for k in self.args])  # single spaces
        args += "".join([f" --{k} {v}" for k, v in self.kwargs.items()])

        # Ensure that the puppet call will return 0 in case of exit code 2
        if salt.utils.platform.is_windows():
            return "cmd /V:ON /c {} {} ^& if !ERRORLEVEL! EQU 2 (EXIT 0) ELSE (EXIT /B)".format(
                cmd, args
            )
        return f"({cmd} {args}) || test $? -eq 2"

    def arguments(self, args=None):
        """
        Read in arguments for the current subcommand. These are added to the
        cmd line without '--' appended. Any others are redirected as standard
        options with the double hyphen prefixed.
        """
        # permits deleting elements rather than using slices
        args = args and list(args) or []

        # match against all known/supported subcmds
        if self.subcmd == "apply":
            # apply subcommand requires a manifest file to execute
            self.subcmd_args = [args[0]]
            del args[0]

        if self.subcmd == "agent":
            # no arguments are required
            args.extend(["test"])

        # finally do this after subcmd has been matched for all remaining args
        self.args = args


def run(*args, **kwargs):
    """
    Execute a puppet run and return a dict with the stderr, stdout,
    return code, etc. The first positional argument given is checked as a
    subcommand. Following positional arguments should be ordered with arguments
    required by the subcommand first, followed by non-keyword arguments.
    Tags are specified by a tag keyword and comma separated list of values. --
    http://docs.puppetlabs.com/puppet/latest/reference/lang_tags.html

    CLI Examples:

    .. code-block:: bash

        salt '*' puppet.run
        salt '*' puppet.run tags=basefiles::edit,apache::server
        salt '*' puppet.run agent onetime no-daemonize no-usecacheonfailure no-splay ignorecache
        salt '*' puppet.run debug
        salt '*' puppet.run apply /a/b/manifest.pp modulepath=/a/b/modules tags=basefiles::edit,apache::server
    """
    puppet = _Puppet()

    # new args tuple to filter out agent/apply for _Puppet.arguments()
    buildargs = ()
    for arg in args:
        # based on puppet documentation action must come first. making the same
        # assertion. need to ensure the list of supported cmds here matches
        # those defined in _Puppet.arguments()
        if arg in ["agent", "apply"]:
            puppet.subcmd = arg
        else:
            buildargs += (arg,)
    # args will exist as an empty list even if none have been provided
    puppet.arguments(buildargs)

    puppet.kwargs.update(salt.utils.args.clean_kwargs(**kwargs))

    ret = __salt__["cmd.run_all"](repr(puppet), python_shell=True)
    return ret


def noop(*args, **kwargs):
    """
    Execute a puppet noop run and return a dict with the stderr, stdout,
    return code, etc. Usage is the same as for puppet.run.

    CLI Example:

    .. code-block:: bash

        salt '*' puppet.noop
        salt '*' puppet.noop tags=basefiles::edit,apache::server
        salt '*' puppet.noop debug
        salt '*' puppet.noop apply /a/b/manifest.pp modulepath=/a/b/modules tags=basefiles::edit,apache::server
    """
    args += ("noop",)
    return run(*args, **kwargs)


def enable():
    """
    .. versionadded:: 2014.7.0

    Enable the puppet agent

    CLI Example:

    .. code-block:: bash

        salt '*' puppet.enable
    """
    puppet = _Puppet()

    if os.path.isfile(puppet.disabled_lockfile):
        try:
            os.remove(puppet.disabled_lockfile)
        except OSError as exc:
            msg = f"Failed to enable: {exc}"
            log.error(msg)
            raise CommandExecutionError(msg)
        else:
            return True
    return False


def disable(message=None):
    """
    .. versionadded:: 2014.7.0

    Disable the puppet agent

    message
        .. versionadded:: 2015.5.2

        Disable message to send to puppet

    CLI Example:

    .. code-block:: bash

        salt '*' puppet.disable
        salt '*' puppet.disable 'Disabled, contact XYZ before enabling'
    """

    puppet = _Puppet()

    if os.path.isfile(puppet.disabled_lockfile):
        return False
    else:
        with salt.utils.files.fopen(puppet.disabled_lockfile, "w") as lockfile:
            try:
                # Puppet chokes when no valid json is found
                msg = (
                    f'{{"disabled_message":"{message}"}}'
                    if message is not None
                    else "{}"
                )
                lockfile.write(salt.utils.stringutils.to_str(msg))
                lockfile.close()
                return True
            except OSError as exc:
                msg = f"Failed to disable: {exc}"
                log.error(msg)
                raise CommandExecutionError(msg)


def status():
    """
    .. versionadded:: 2014.7.0

    Display puppet agent status

    CLI Example:

    .. code-block:: bash

        salt '*' puppet.status
    """
    puppet = _Puppet()

    if os.path.isfile(puppet.disabled_lockfile):
        return "Administratively disabled"

    if os.path.isfile(puppet.run_lockfile):
        try:
            with salt.utils.files.fopen(puppet.run_lockfile, "r") as fp_:
                pid = int(salt.utils.stringutils.to_unicode(fp_.read()))
                os.kill(pid, 0)  # raise an OSError if process doesn't exist
        except (OSError, ValueError):
            return "Stale lockfile"
        else:
            return "Applying a catalog"

    if os.path.isfile(puppet.agent_pidfile):
        try:
            with salt.utils.files.fopen(puppet.agent_pidfile, "r") as fp_:
                pid = int(salt.utils.stringutils.to_unicode(fp_.read()))
                os.kill(pid, 0)  # raise an OSError if process doesn't exist
        except (OSError, ValueError):
            return "Stale pidfile"
        else:
            return "Idle daemon"

    return "Stopped"


def summary():
    """
    .. versionadded:: 2014.7.0

    Show a summary of the last puppet agent run

    CLI Example:

    .. code-block:: bash

        salt '*' puppet.summary
    """

    puppet = _Puppet()

    try:
        with salt.utils.files.fopen(puppet.lastrunfile, "r") as fp_:
            report = salt.utils.yaml.safe_load(fp_)
        result = {}

        if "time" in report:
            try:
                result["last_run"] = datetime.datetime.fromtimestamp(
                    int(report["time"]["last_run"])
                ).isoformat()
            except (TypeError, ValueError, KeyError):
                result["last_run"] = "invalid or missing timestamp"

            result["time"] = {}
            for key in ("total", "config_retrieval"):
                if key in report["time"]:
                    result["time"][key] = report["time"][key]

        if "resources" in report:
            result["resources"] = report["resources"]

    except salt.utils.yaml.YAMLError as exc:
        raise CommandExecutionError(f"YAML error parsing puppet run summary: {exc}")
    except OSError as exc:
        raise CommandExecutionError(f"Unable to read puppet run summary: {exc}")

    return result


def plugin_sync():
    """
    Runs a plugin sync between the puppet master and agent

    CLI Example:

    .. code-block:: bash

        salt '*' puppet.plugin_sync
    """
    ret = __salt__["cmd.run"]("puppet plugin download")

    if not ret:
        return ""
    return ret


def facts(puppet=False):
    """
    Run facter and return the results

    CLI Example:

    .. code-block:: bash

        salt '*' puppet.facts
    """
    ret = {}
    opt_puppet = "--puppet" if puppet else ""
    cmd_ret = __salt__["cmd.run_all"](f"facter {opt_puppet}")

    if cmd_ret["retcode"] != 0:
        raise CommandExecutionError(cmd_ret["stderr"])

    output = cmd_ret["stdout"]

    # Loop over the facter output and  properly
    # parse it into a nice dictionary for using
    # elsewhere
    for line in output.splitlines():
        if not line:
            continue
        fact, value = _format_fact(line)
        if not fact:
            continue
        ret[fact] = value
    return ret


def fact(name, puppet=False):
    """
    Run facter for a specific fact

    CLI Example:

    .. code-block:: bash

        salt '*' puppet.fact kernel
    """
    opt_puppet = "--puppet" if puppet else ""
    ret = __salt__["cmd.run_all"](f"facter {opt_puppet} {name}", python_shell=False)

    if ret["retcode"] != 0:
        raise CommandExecutionError(ret["stderr"])

    if not ret["stdout"]:
        return ""
    return ret["stdout"]

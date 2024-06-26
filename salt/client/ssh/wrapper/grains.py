"""
Return/control aspects of the grains data
"""

import math

import salt.utils.data
import salt.utils.dictupdate
import salt.utils.json
from salt.defaults import DEFAULT_TARGET_DELIM

# Seed the grains dict so cython will build
__grains__ = {}


def _serial_sanitizer(instr):
    """
    Replaces the last 1/4 of a string with X's
    """
    length = len(instr)
    index = int(math.floor(length * 0.75))
    return "{}{}".format(instr[:index], "X" * (length - index))


def _fqdn_sanitizer(x):
    return "MINION.DOMAINNAME"


def _hostname_sanitizer(x):
    return "MINION"


def _domainname_sanitizer(x):
    return "DOMAINNAME"


# A dictionary of grain -> function mappings for sanitizing grain output. This
# is used when the 'sanitize' flag is given.
_SANITIZERS = {
    "serialnumber": _serial_sanitizer,
    "domain": _domainname_sanitizer,
    "fqdn": _fqdn_sanitizer,
    "id": _fqdn_sanitizer,
    "host": _hostname_sanitizer,
    "localhost": _hostname_sanitizer,
    "nodename": _hostname_sanitizer,
}


def get(key, default="", delimiter=DEFAULT_TARGET_DELIM, ordered=True):
    """
    Attempt to retrieve the named value from grains, if the named value is not
    available return the passed default. The default return is an empty string.

    The value can also represent a value in a nested dict using a ":" delimiter
    for the dict. This means that if a dict in grains looks like this::

        {'pkg': {'apache': 'httpd'}}

    To retrieve the value associated with the apache key in the pkg dict this
    key can be passed::

        pkg:apache

    CLI Example:

    .. code-block:: bash

        salt '*' grains.get pkg:apache
    """
    if ordered is True:
        grains = __grains__.value()
    else:
        grains = salt.utils.json.loads(salt.utils.json.dumps(__grains__.value()))
    return salt.utils.data.traverse_dict_and_list(grains, key, default, delimiter)


def has_value(key):
    """
    Determine whether a named value exists in the grains dictionary.

    Given a grains dictionary that contains the following structure::

        {'pkg': {'apache': 'httpd'}}

    One would determine if the apache key in the pkg dict exists by::

        pkg:apache

    CLI Example:

    .. code-block:: bash

        salt '*' grains.has_value pkg:apache
    """
    return (
        True
        if salt.utils.data.traverse_dict_and_list(__grains__, key, False)
        else False
    )


def items(sanitize=False):
    """
    Return all of the minion's grains

    CLI Example:

    .. code-block:: bash

        salt '*' grains.items

    Sanitized CLI Example:

    .. code-block:: bash

        salt '*' grains.items sanitize=True
    """
    if salt.utils.data.is_true(sanitize):
        out = dict(__grains__.value())
        for key, func in _SANITIZERS.items():
            if key in out:
                out[key] = func(out[key])
        return out
    else:
        return __grains__.value()


def item(*args, **kwargs):
    """
    Return one or more grains

    CLI Example:

    .. code-block:: bash

        salt '*' grains.item os
        salt '*' grains.item os osrelease oscodename

    Sanitized CLI Example:

    .. code-block:: bash

        salt '*' grains.item host sanitize=True
    """
    ret = {}
    for arg in args:
        try:
            ret[arg] = __grains__[arg]
        except KeyError:
            pass
    if salt.utils.data.is_true(kwargs.get("sanitize")):
        for arg, func in _SANITIZERS.items():
            if arg in ret:
                ret[arg] = func(ret[arg])
    return ret


def ls():  # pylint: disable=C0103
    """
    Return a list of all available grains

    CLI Example:

    .. code-block:: bash

        salt '*' grains.ls
    """
    return sorted(__grains__)


def filter_by(lookup_dict, grain="os_family", merge=None, default="default", base=None):
    """
    .. versionadded:: 0.17.0

    Look up the given grain in a given dictionary for the current OS and return
    the result

    Although this may occasionally be useful at the CLI, the primary intent of
    this function is for use in Jinja to make short work of creating lookup
    tables for OS-specific data. For example:

    .. code-block:: jinja

        {% set apache = salt['grains.filter_by']({
            'Debian': {'pkg': 'apache2', 'srv': 'apache2'},
            'RedHat': {'pkg': 'httpd', 'srv': 'httpd'},
        }, default='Debian') %}

        myapache:
          pkg.installed:
            - name: {{ apache.pkg }}
          service.running:
            - name: {{ apache.srv }}

    Values in the lookup table may be overridden by values in Pillar. An
    example Pillar to override values in the example above could be as follows:

    .. code-block:: yaml

        apache:
          lookup:
            pkg: apache_13
            srv: apache

    The call to ``filter_by()`` would be modified as follows to reference those
    Pillar values:

    .. code-block:: jinja

        {% set apache = salt['grains.filter_by']({
            ...
        }, merge=salt['pillar.get']('apache:lookup')) %}


    :param lookup_dict: A dictionary, keyed by a grain, containing a value or
        values relevant to systems matching that grain. For example, a key
        could be the grain for an OS and the value could the name of a package
        on that particular OS.

        .. versionchanged:: 2016.11.0

            The dictionary key could be a globbing pattern. The function will
            return the corresponding ``lookup_dict`` value where grain value
            matches the pattern. For example:

            .. code-block:: bash

                # this will render 'got some salt' if Minion ID begins from 'salt'
                salt '*' grains.filter_by '{salt*: got some salt, default: salt is not here}' id

    :param grain: The name of a grain to match with the current system's
        grains. For example, the value of the "os_family" grain for the current
        system could be used to pull values from the ``lookup_dict``
        dictionary.

        .. versionchanged:: 2016.11.0

            The grain value could be a list. The function will return the
            ``lookup_dict`` value for a first found item in the list matching
            one of the ``lookup_dict`` keys.

    :param merge: A dictionary to merge with the results of the grain selection
        from ``lookup_dict``. This allows Pillar to override the values in the
        ``lookup_dict``. This could be useful, for example, to override the
        values for non-standard package names such as when using a different
        Python version from the default Python version provided by the OS
        (e.g., ``python26-mysql`` instead of ``python-mysql``).

    :param default: default lookup_dict's key used if the grain does not exists
        or if the grain value has no match on lookup_dict. If unspecified
        the value is "default".

        .. versionadded:: 2014.1.0

    :param base: A lookup_dict key to use for a base dictionary. The
        grain-selected ``lookup_dict`` is merged over this and then finally
        the ``merge`` dictionary is merged. This allows common values for
        each case to be collected in the base and overridden by the grain
        selection dictionary and the merge dictionary. Default is unset.

        .. versionadded:: 2015.8.11,2016.3.2

    CLI Example:

    .. code-block:: bash

        salt '*' grains.filter_by '{Debian: Debheads rule, RedHat: I love my hat}'
        # this one will render {D: {E: I, G: H}, J: K}
        salt '*' grains.filter_by '{A: B, C: {D: {E: F, G: H}}}' 'xxx' '{D: {E: I}, J: K}' 'C'
        # next one renders {A: {B: G}, D: J}
        salt '*' grains.filter_by '{default: {A: {B: C}, D: E}, F: {A: {B: G}}, H: {D: I}}' 'xxx' '{D: J}' 'F' 'default'
        # next same as above when default='H' instead of 'F' renders {A: {B: C}, D: J}
    """
    return salt.utils.data.filter_by(
        lookup_dict=lookup_dict,
        lookup=grain,
        traverse=__grains__.value(),
        merge=merge,
        default=default,
        base=base,
    )

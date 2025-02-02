# pylint: disable=redefined-builtin
import datetime
from collections import defaultdict

from ..exceptions import RedisError
from ..utils import bool_ok
from ..utils import dict_merge
from ..utils import list_or_args
from ..utils import nativestr
from ..utils import NodeFlag
from ..utils import string_keys_to_dict


class BitField:
    """
    The command treats a Redis string as a array of bits,
    and is capable of addressing specific integer fields
    of varying bit widths and arbitrary non (necessary) aligned offset.

    The supported types are up to 64 bits for signed integers,
    and up to 63 bits for unsigned integers.

    Offset can be num prefixed with `#` character or num directly,
    for command detail you should see: https://redis.io/commands/bitfield
    """

    def __init__(self, redis_client, key):
        self._command_stack = ['BITFIELD', key]
        self.redis = redis_client

    def __del__(self):
        self._command_stack.clear()

    def set(self, type, offset, value):
        """
        Set the specified bit field and returns its old value.
        """
        self._command_stack.extend(['SET', type, offset, value])
        return self

    def get(self, type, offset):
        """
        Returns the specified bit field.
        """
        self._command_stack.extend(['GET', type, offset])
        return self

    def incrby(self, type, offset, increment):
        """
        Increments or decrements (if a negative increment is given)
        the specified bit field and returns the new value.
        """
        self._command_stack.extend(['INCRBY', type, offset, increment])
        return self

    def overflow(self, type='SAT'):
        """
        fine-tune the behavior of the increment or decrement overflow,
        have no effect unless used before `incrby`
        three types are available: WRAP|SAT|FAIL
        """
        self._command_stack.extend(['OVERFLOW', type])
        return self

    async def exc(self):
        """execute commands in command stack"""
        return await self.redis.execute_command(*self._command_stack)


class StringsCommandMixin:
    # pylint: disable=too-many-public-methods
    RESPONSE_CALLBACKS = dict_merge(
        string_keys_to_dict(
            'MSETNX PSETEX SETEX SETNX',
            bool,
        ),
        string_keys_to_dict(
            'BITCOUNT BITPOS DECRBY GETBIT INCRBY '
            'STRLEN SETBIT', int,
        ),
        {
            'INCRBYFLOAT': float,
            'MSET': bool_ok,
            'SET': lambda r: r and nativestr(r) == 'OK',
        },
    )

    async def append(self, key, value):
        """
        Appends the string ``value`` to the value at ``key``. If ``key``
        doesn't already exist, create it with a value of ``value``.
        Returns the new length of the value at ``key``.
        """
        return await self.execute_command('APPEND', key, value)

    async def bitcount(self, key, start=None, end=None):
        """
        Returns the count of set bits in the value of ``key``.  Optional
        ``start`` and ``end`` paramaters indicate which bytes to consider
        """
        params = [key]
        if start is not None and end is not None:
            params.append(start)
            params.append(end)
        elif ((start is not None and end is None)
                or (end is not None and start is None)):
            raise RedisError('Both start and end must be specified')
        return await self.execute_command('BITCOUNT', *params)

    async def bitop(self, operation, dest, *keys):
        """
        Perform a bitwise operation using ``operation`` between ``keys`` and
        store the result in ``dest``.
        """
        return await self.execute_command('BITOP', operation, dest, *keys)

    async def bitpos(self, key, bit, start=None, end=None):
        """
        Return the position of the first bit set to 1 or 0 in a string.
        ``start`` and ``end`` difines search range. The range is interpreted
        as a range of bytes and not a range of bits, so start=0 and end=2
        means to look at the first three bytes.
        """
        if bit not in (0, 1):
            raise RedisError('bit must be 0 or 1')
        params = [key, bit]

        if start is not None:
            params.append(start)

        if start is not None and end is not None:
            params.append(end)
        elif start is None and end is not None:
            raise RedisError('start argument is not set, '
                             'when end is specified')
        return await self.execute_command('BITPOS', *params)

    def bitfield(self, key):
        return BitField(self, key)

    async def decr(self, name, amount=1):
        """
        Decrements the value of ``key`` by ``amount``.  If no key exists,
        the value will be initialized as 0 - ``amount``
        """
        return await self.execute_command('DECRBY', name, amount)

    async def get(self, name):
        """
        Return the value at key ``name``, or None if the key doesn't exist
        """
        return await self.execute_command('GET', name)

    async def getbit(self, name, offset):
        'Returns a boolean indicating the value of ``offset`` in ``name``'
        return await self.execute_command('GETBIT', name, offset)

    async def getrange(self, key, start, end):
        """
        Returns the substring of the string value stored at ``key``,
        determined by the offsets ``start`` and ``end`` (both are inclusive)
        """
        return await self.execute_command('GETRANGE', key, start, end)

    async def getset(self, name, value):
        """
        Sets the value at key ``name`` to ``value``
        and returns the old value at key ``name`` atomically.
        """
        return await self.execute_command('GETSET', name, value)

    async def incr(self, name, amount=1):
        """
        Increments the value of ``key`` by ``amount``.  If no key exists,
        the value will be initialized as ``amount``
        """
        return await self.execute_command('INCRBY', name, amount)

    async def incrby(self, name, amount=1):
        """
        Increments the value of ``key`` by ``amount``.  If no key exists,
        the value will be initialized as ``amount``
        """

        # An alias for ``incr()``, because it is already implemented
        # as INCRBY redis command.
        return await self.incr(name, amount)

    async def incrbyfloat(self, name, amount=1.0):
        """
        Increments the value at key ``name`` by floating ``amount``.
        If no key exists, the value will be initialized as ``amount``
        """
        return await self.execute_command('INCRBYFLOAT', name, amount)

    async def mget(self, keys, *args):
        """
        Returns a list of values ordered identically to ``keys``
        """
        args = list_or_args(keys, args)
        return await self.execute_command('MGET', *args)

    async def mset(self, *args, **kwargs):
        """
        Sets key/values based on a mapping. Mapping can be supplied as a single
        dictionary argument or as kwargs.
        """
        if args:
            if len(args) != 1 or not isinstance(args[0], dict):
                raise RedisError('MSET requires **kwargs or a single dict arg')
            kwargs.update(args[0])
        items = []
        for pair in iter(kwargs.items()):
            items.extend(pair)
        return await self.execute_command('MSET', *items)

    async def msetnx(self, *args, **kwargs):
        """
        Sets key/values based on a mapping if none of the keys are already set.
        Mapping can be supplied as a single dictionary argument or as kwargs.
        Returns a boolean indicating if the operation was successful.
        """
        if args:
            if len(args) != 1 or not isinstance(args[0], dict):
                raise RedisError('MSETNX requires **kwargs or a single '
                                 'dict arg')
            kwargs.update(args[0])
        items = []
        for pair in iter(kwargs.items()):
            items.extend(pair)
        return await self.execute_command('MSETNX', *items)

    async def psetex(self, name, time_ms, value):
        """
        Set the value of key ``name`` to ``value`` that expires in ``time_ms``
        milliseconds. ``time_ms`` can be represented by an integer or a Python
        timedelta object
        """
        if isinstance(time_ms, datetime.timedelta):
            ms = int(time_ms.microseconds / 1000)
            time_ms = (time_ms.seconds + time_ms.days * 24 * 3600) * 1000 + ms
        return await self.execute_command('PSETEX', name, time_ms, value)

    async def set(self, name, value, ex=None, px=None, keepttl=False, nx=False, xx=False):
        """
        Set the value at key ``name`` to ``value``

        ``ex`` sets an expire flag on key ``name`` for ``ex`` seconds.

        ``px`` sets an expire flag on key ``name`` for ``px`` milliseconds.

        ``keepttl`` if set to True, retain the time to live associated with the
            key.

        ``nx`` if set to True, set the value at key ``name`` to ``value`` if it
            does not already exist.

        ``xx`` if set to True, set the value at key ``name`` to ``value`` if it
            already exists.
        """
        pieces = [name, value]
        if ex is not None:
            pieces.append('EX')
            if isinstance(ex, datetime.timedelta):
                ex = ex.seconds + ex.days * 24 * 3600
            pieces.append(ex)
        if px is not None:
            pieces.append('PX')
            if isinstance(px, datetime.timedelta):
                ms = int(px.microseconds / 1000)
                px = (px.seconds + px.days * 24 * 3600) * 1000 + ms
            pieces.append(px)

        if keepttl:
            pieces.append('KEEPTTL')
        if nx:
            pieces.append('NX')
        if xx:
            pieces.append('XX')
        return await self.execute_command('SET', *pieces)

    async def setbit(self, name, offset, value):
        """
        Flag the ``offset`` in ``name`` as ``value``. Returns a boolean
        indicating the previous value of ``offset``.
        """
        value = 1 if value else 0
        return await self.execute_command('SETBIT', name, offset, value)

    async def setex(self, name, time, value):
        """
        Set the value of key ``name`` to ``value`` that expires in ``time``
        seconds. ``time`` can be represented by an integer or a Python
        timedelta object.
        """
        if isinstance(time, datetime.timedelta):
            time = time.seconds + time.days * 24 * 3600
        return await self.execute_command('SETEX', name, time, value)

    async def setnx(self, name, value):
        """
        Sets the value of key ``name`` to ``value`` if key doesn't exist
        """
        return await self.execute_command('SETNX', name, value)

    async def setrange(self, name, offset, value):
        """
        Overwrite bytes in the value of ``name`` starting at ``offset`` with
        ``value``. If ``offset`` plus the length of ``value`` exceeds the
        length of the original value, the new value will be larger than before.
        If ``offset`` exceeds the length of the original value, null bytes
        will be used to pad between the end of the previous value and the start
        of what's being injected.

        Returns the length of the new string.
        """
        return await self.execute_command('SETRANGE', name, offset, value)

    async def strlen(self, name):
        """Returns the number of bytes stored in the value of ``name``"""
        return await self.execute_command('STRLEN', name)

    async def substr(self, name, start, end=-1):
        """
        Returns a substring of the string at key ``name``. ``start`` and ``end``
        are 0-based integers specifying the portion of the string to return.
        """
        return await self.execute_command('SUBSTR', name, start, end)


class ClusterStringsCommandMixin(StringsCommandMixin):

    NODES_FLAGS = {
        'BITOP': NodeFlag.BLOCKED,
    }

    @staticmethod
    def _get_hash_tag_from_key(key):
        """
        Returns the "hash tag" for a key or None if one does not exist.

        For the spec, see the following documentation:
        https://redis.io/topics/cluster-tutorial#redis-cluster-data-sharding
        """
        if key.count('{') != 1 or key.count('}') != 1:
            # no hash tag
            return None
        if key.index('{') >= key.index('}'):
            # invalid hash tag
            return None
        return key.split('{', 2)[1].split('}', 2)[0]

    async def mget(self, keys, *args):
        """
        Returns a list of values ordered identically to ``keys``

        Cluster impl:
            Find groups of keys with the same hash tag and execute an MGET for
            each group. Execute individual GETs for all other keys.

            For a definition of "hash tags", see
            https://redis.io/topics/cluster-tutorial#redis-cluster-data-sharding

            Operation will be atomic only if all keys belong to a single
            hash tag.
        """
        ordered_keys = list_or_args(keys, args)
        res_mapping = {}  # key -> res
        hash_tag_slots = defaultdict(list)

        for key in ordered_keys:
            hash_tag = self._get_hash_tag_from_key(key)
            if hash_tag is not None:
                # enqueue this key to be fetched in a group later
                hash_tag_slots[hash_tag].append(key)
            else:
                # a loose key without a hash tag, can't use MGET
                res_mapping[key] = await self.get(key)

        for mget_keys in hash_tag_slots.values():
            mget_res = await self.execute_command('MGET', *mget_keys)
            for key, res in zip(mget_keys, mget_res):
                res_mapping[key] = res

        return [res_mapping[k] for k in ordered_keys]

    async def mset(self, *args, **kwargs):
        """
        Sets key/values based on a mapping. Mapping can be supplied as a single
        dictionary argument or as kwargs.

        Cluster impl:
            Find groups of keys with the same hash tag and execute an MSET for
            each group. Execute individual SETs for all other key/value pairs.

            For a definition of "hash tags", see
            https://redis.io/topics/cluster-tutorial#redis-cluster-data-sharding

            Operation will be atomic only if all keys belong to a single
            hash tag.
        """
        if args:
            if len(args) != 1 or not isinstance(args[0], dict):
                raise RedisError('MSET requires **kwargs or a single dict arg')
            kwargs.update(args[0])

        hash_tag_slots = defaultdict(list)
        for pair in iter(kwargs.items()):
            key, v = pair
            hash_tag = self._get_hash_tag_from_key(key)
            if hash_tag is not None:
                # enqueue this key to be fetched in a group later
                hash_tag_slots[hash_tag].extend(pair)
            else:
                # a loose key without a hash tag, can't use MSET
                await self.set(key, v)

        for mset_items in hash_tag_slots.values():
            await self.execute_command('MSET', *mset_items)

        return True

    async def msetnx(self, *args, **kwargs):
        """
        Sets key/values based on a mapping if none of the keys are already set.
        Mapping can be supplied as a single dictionary argument or as kwargs.
        Returns a boolean indicating if the operation was successful.

        Clutser impl:
            Itterate over all items and do GET to determine if all keys do not exists.
            If true then call mset() on all keys.
        """
        if args:
            if len(args) != 1 or not isinstance(args[0], dict):
                raise RedisError(
                    'MSETNX requires **kwargs or a single dict arg')
            kwargs.update(args[0])

        # Itterate over all items and fail fast if one value is True.
        for k, _ in kwargs.items():
            if await self.get(k):
                return False

        return await self.mset(**kwargs)

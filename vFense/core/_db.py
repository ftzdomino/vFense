import logging, logging.config
from vFense._constants import VFENSE_LOGGING_CONFIG
from vFense.core._db_constants import DbInfoKeys
from vFense.core.decorators import time_it, return_status_tuple, catch_it
from vFense.db.client import db_create_close, r

logging.config.fileConfig(VFENSE_LOGGING_CONFIG)
logger = logging.getLogger('vfense_api')


@catch_it({})
@db_create_close
def retrieve_collections(conn=None):
    """Retrieve a list of collections
    Basic Usage:
        >>> from vFense.core._db import retrieve_collections
        >>> retrieve_collections()

    Returns:
        List
    """
    data = (
        r
        .table_list()
        .run(conn)
    )
    return data

@catch_it({})
@db_create_close
def retrieve_primary_key(collection, conn=None):
    """Retrieve the primary key for a collection.
    Args:
        collection (str):  The table aka collection you are doing the query against.

    Basic Usage:
        >>> from vFense.core._db import retrieve_primary_key
        >>> collection = 'users'
        >>> retrieve_primary_key(collection)

    Returns:
        String
    """
    data = (
        r
        .table(collection)
        .info()
        .pluck(DbInfoKeys.PRIMARY_KEY)
        .run(conn)
    )
    if data:
        data = data[DbInfoKeys.PRIMARY_KEY]

    return data

@catch_it({})
@db_create_close
def retrieve_indexes(collection, conn=None):
    """Retrieve the list of indexes for a collection.
    Args:
        collection (str):  The table aka collection you are doing the query against.

    Basic Usage:
        >>> from vFense.core._db import retrieve_indexes
        >>> collection, = 'users'
        >>> retrieve_indexes(collection)

    Returns:
        List
    """
    data = (
        r
        .table(collection)
        .info()
        .pluck(DbInfoKeys.INDEXES)
        .run(conn)
    )
    if data:
        data = data[DbInfoKeys.INDEXES]

    return data

@catch_it({})
@db_create_close
def retrieve_object(primary_key, collection, conn=None):
    """Retrieve object by primary key and collection.
    Args:
        primary_key (str):  The primary key that you are doing a get against.
        collection (str):  The table aka collection you are doing the query against.

    Basic Usage:
        >>> from vFense.core._db import retrieve_object
        >>> collection, = 'users'
        >>> primary_key = 'admin'
        >>> retrieve_object(primary_key, collection)

    Returns:
        Dictionary
    """
    data = (
        r
        .table(collection)
        .get(primary_key)
        .run(conn)
    )

    return data

@catch_it(False)
@db_create_close
def db_exist(name=None, conn=None):
    """Verify if datbase exist
    Args:
        name (str): The name of the database:
            default=conn.db

    Basic Usage:
        >>> from vFense.core._db import db_exist
        >>> db_exist()

    Returns:
        Boolean
    """
    databases = (
        r
        .db_list()
        .run(conn)
    )
    if conn.db in databases:
        db_exist = True
    else:
        db_exist = False

    return db_exist

@time_it
@catch_it(False)
@db_create_close
def object_exist(primary_key, collection, conn=None):
    """Verify if an object exist in the database, by primary key.
    Args:
        primary_key (str):  The primary key that you are doing a get against.
        collection (str):  The table aka collection you are doing the query against.

    Basic Usage:
        >>> from vFense.core._db import object_exist
        >>> collection, = 'users'
        >>> primary_key = 'admin'
        >>> object_exist(primary_key, collection)

    Returns:
        Boolean
    """
    exist = False
    is_empty = (
        r
        .table(collection)
        .get_all(primary_key)
        .is_empty()
        .run(conn)
    )
    if not is_empty:
        exist = True

    return exist

@catch_it({})
@db_create_close
def create_db(name=None, conn=None):
    """Create a new db
    Args:
        name (str):  The name of the collection you are creating.
            default=conn.db

    Basic Usage:
        >>> from vFense.core._db import create_db
        >>> name = "vFense"
        >>> create_db(name)

    Returns:
        Boolean
    """
    if not name:
        name = conn.db

    data = (
        r
        .db_create(name)
        .run(conn)
    )

    return data

@catch_it({})
@db_create_close
def create_collection(name, primary_key, conn=None):
    """Create a new collection
    Args:
        name (str):  The name of the collection you are creating.
        primary_key (str):  The primary key of this collection.

    Basic Usage:
        >>> from vFense.core._db import create_collection
        >>> name = "apps_per_agent"
        >>> key = "id"
        >>> create_collection(name, key)

    Returns:
        Dictionary
    """
    data = (
        r
        .table_create(name, primary_key=primary_key)
        .run(conn)
    )

    return data

@time_it
@catch_it({})
@db_create_close
@return_status_tuple
def insert_data_in_table(data, collection, conn=None):
    """Insert data in a collection
    Args:
        data (list|dict): List of dictionaries or a dictionary of the data
            you are inserting.
        collection (str): The name of the collection you are removing all data from.

    Basic Usage:
        >>> from vFense.core._db import insert_data_in_table
        >>> data = [{'name': 'foo'}]
        >>> collection = 'agents'
        >>> insert_data_in_table(data, collection)

    Returns:
        Tuple (status_code, count, error, generated ids)
        >>> (2001, 1, None, [])
    """
    results = (
        r
        .table(collection)
        .insert(data, conflict="replace")
        .run(conn, no_reply=True, durability='soft')
    )

    return results

@time_it
@catch_it({})
@db_create_close
@return_status_tuple
def delete_data_in_table(primary_key, collection, conn=None):
    """Delete data in a collection
    Args:
        primary_key (str): The primary key of the collection
            you are searching for,
        collection (str): The name of the collection you are removing all data from.

    Basic Usage:
        >>> from vFense.core._db import delete_data_in_table
        >>> primary_key = 'default'
        >>> collection = 'agents'
        >>> delete_data_in_table(primary_key, collection)

    Returns:
        Tuple (status_code, count, error, generated ids)
        >>> (2001, 1, None, [])
    """
    results = (
        r
        .table(collection)
        .get(primary_key)
        .delete()
        .run(conn)
    )

    return results

@time_it
@catch_it({})
@db_create_close
@return_status_tuple
def update_data_in_table(primary_key, data, collection, conn=None):
    """Update data by the primary key of the collection
    Args:
        primary_key (str): The primary key, of the object you are searching.
        data (dict): Dictionary of the data you are updating.
            you are inserting.
        collection (str): The name of the collection you are updating.

    Basic Usage:
        >>> from vFense.core._db import update_data_in_table
        >>> primary_key = 'default'
        >>> data = {'enabled': 'no'}
        >>> collection = 'users'
        >>> update_data_in_table(primary_key, data, collection)

    Returns:
        Tuple (status_code, count, error, generated ids)
        >>> (2001, 1, None, [])
    """
    results = (
        r
        .table(collection)
        .get(primary_key)
        .update(data)
        .run(conn, no_reply=True, durability='soft')
    )

    return results

@time_it
@catch_it({})
@db_create_close
@return_status_tuple
def delete_all_in_table(collection, conn=None):
    """Delete all data in a collection
        WARNING, ALL DATA INSIDE COLLECTION WILL BE DELETED!!!
    Args:
        collection (str): The name of the collection you are removing all data from.

    Basic Usage:
        >>> from vFense.core._db import delete_all_in_table
        >>> collection = 'agents'
        >>> delete_all_in_table(collection)

    Returns:
        Tuple (status_code, count, error, generated ids)
        >>> (2001, 1, None, [])
    """
    data = (
        r
        .table(collection)
        .delete()
        .run(conn, no_reply=True, durability='soft')
    )

    return data

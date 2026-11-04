"""Códigos de retorno WITSML 1.4.1 y sus mensajes base.

Fuente normativa: WITSML STORE API v1.4.1, Apéndice A (Defined Return Values).
``WMLS_GetBaseMsg`` devuelve exactamente estos textos.
"""

from __future__ import annotations

from enum import IntEnum


class WmlsCode(IntEnum):
    SUCCESS = 1
    PARTIAL_SUCCESS = 2
    SUCCESS_WITH_WARNINGS = 1001
    PARTIAL_SUCCESS_WITH_WARNINGS = 1002

    MISSING_PLURAL_ROOT = -401
    INVALID_MAX_RETURN_NODES = -402
    MISSING_WITSML_NAMESPACE = -403
    INVALID_CLIENT_SCHEMA_VERSION = -404
    DUPLICATE_OBJECT = -405
    MISSING_PARENTAGE_UID = -406
    MISSING_WMLTYPE = -407
    MISSING_INPUT_TEMPLATE = -408
    INPUT_TEMPLATE_NONCONFORMING = -409
    EMPTY_ELEMENT_NONCONFORMING = -410
    PARAMETERS_NOT_ENCODED = -411
    INPUT_OBJECT_NOT_COMPLIANT = -412
    OBJECT_NOT_SUPPORTED = -413
    INSUFFICIENT_RIGHTS = -414
    MISSING_UID = -415
    EMPTY_UID = -416
    EMPTY_UOM = -417
    MISSING_ELEMENT_UID_FOR_DELETE = -418
    EMPTY_NON_RECURRING = -419
    EMPTY_MANDATORY_NODE = -420
    MUST_RETAIN_RECURRING = -421
    INVALID_RETURN_VALUE = -422
    DATA_VERSION_NOT_SUPPORTED = -423
    MISSING_DATA_VERSION = -424
    INVALID_OPTION_FOR_GROWING_ONLY = -425
    COMPRESSED_INPUT_NONCONFORMING = -426
    INVALID_OPTIONS_COMBINATION = -427
    INVALID_MINIMUM_QUERY = -428
    RECURRING_LOG_DATA = -429
    DATA_ITEM_NOT_SUPPORTED = -430
    DATA_OBJECT_ITEM_NOT_SUPPORTED = -431
    NOT_BOTTOM_LEVEL = -432
    OBJECT_NOT_EXIST = -433
    MISSING_COLUMN_IDENTIFIERS = -434
    INDEX_RANGE_SPECIFIED = -436
    COLUMN_IDENTIFIER_SPECIFIED = -437
    RECURRING_ITEMS_INCONSISTENT = -438
    RECURRING_ITEMS_EMPTY = -439
    KEYWORD_NOT_SUPPORTED_BY_FUNCTION = -440
    INVALID_KEYWORD_VALUE = -441
    KEYWORD_NOT_SUPPORTED_BY_SERVER = -442
    INVALID_UOM = -443
    MULTIPLE_OBJECTS = -444
    EMPTY_NEW_ELEMENTS = -445
    MISSING_MEASURE_FOR_UOM = -446
    DUPLICATE_COLUMN_IDENTIFIERS = -447
    MISSING_ELEMENT_UID_FOR_UPDATE = -448
    INDEX_CURVE_NOT_FOUND = -449
    MNEMONICS_NOT_UNIQUE = -450
    MISSING_UNIT_LIST = -451
    UNIT_LIST_NOT_MATCH = -452
    MISSING_UNIT_FOR_MEASURE = -453
    INDEX_UOM_NOT_SAME = -454
    WELL_DATUM_NOT_SAME = -455
    MAX_DATA_EXCEEDED = -456
    INDEX_NOT_FIRST = -457
    MIXED_STRUCTURAL_INDICES = -458
    BAD_COLUMN_IDENTIFIER = -459
    COLUMN_IDENTIFIERS_NOT_SAME = -460
    MISSING_MNEMONIC = -461
    MISSING_MNEMONIC_LIST = -462
    NODES_WITH_SAME_INDEX = -463
    CHILD_UID_NOT_UNIQUE = -464
    API_VERSION_NOT_MATCH = -465
    CAPABILITIES_NONCONFORMING = -466
    API_VERSION_NOT_SUPPORTED = -467
    MISSING_DATA_SCHEMA_VERSION = -468
    QUERY_TEMPLATE_NONCONFORMING = -469
    QUERY_NOT_SUPPORTED = -470
    MISSING_CLIENT_USER_AGENT = -472
    SCHEMA_VERSION_NOT_MATCH = -473
    NODE_INDEX_NOT_SPECIFIED = -474
    MISSING_GROWING_SUBSET = -475
    INVALID_OPTION_FOR_CHANGELOG = -476
    MISSING_COLUMN_DESCRIPTION_OR_DATA = -477
    INCORRECT_CASE_PARENT_UID = -478
    CANNOT_DECOMPRESS_QUERY = -479
    ADDING_UPDATING_CURVE = -480
    MISSING_PARENT = -481
    DUPLICATE_MNEMONICS = -482
    UPDATE_TEMPLATE_NONCONFORMING = -483
    MISSING_REQUIRED_DATA = -484
    POLLING_TOO_FAST = -485
    OBJECT_TYPES_DONT_MATCH = -486
    OBJECT_TYPE_NOT_SUPPORTED = -487

    ERROR_ADDING = -1001
    ERROR_READING = -1002
    ERROR_UPDATING = -1003
    ERROR_DELETING = -1004
    TRANSACTION_TIMEOUT = -1005
    MAX_DOCUMENT_SIZE_EXCEEDED = -1006
    ERROR_REPLACING = -1007
    ERROR_DELETING_SIMPLE_CONTENT = -1021
    ROW_DATA_COUNT = -1051
    DELETING_INDEX_CURVE = -1052
    INVALID_COLUMN_INDEX = -1053
    INVALID_REQUEST_LATEST_VALUE = -1054
    INVALID_OPTION_FOR_MUDLOG = -1055


BASE_MESSAGES: dict[int, str] = {
    WmlsCode.SUCCESS: "Function completed successfully.",
    WmlsCode.PARTIAL_SUCCESS: (
        "Partial success: Function completed successfully, but some growing "
        "data-object data-nodes were not returned."
    ),
    WmlsCode.SUCCESS_WITH_WARNINGS: "Function completed successfully with warnings.",
    WmlsCode.PARTIAL_SUCCESS_WITH_WARNINGS: (
        "Partial success: Function completed successfully with warnings, but some "
        "growing data-object data-nodes were not returned."
    ),
    WmlsCode.MISSING_PLURAL_ROOT: "The input template MUST contain a plural root element.",
    WmlsCode.INVALID_MAX_RETURN_NODES: (
        "The value of the OptionsIn keyword of 'maxReturnNodes' MUST be greater than zero."
    ),
    WmlsCode.MISSING_WITSML_NAMESPACE: (
        "A template must include a default namespace declaration for the WITSML namespace."
    ),
    WmlsCode.INVALID_CLIENT_SCHEMA_VERSION: (
        "In the value of the capClient schemaVersion, the oldest Data Schema Version "
        "must be listed first, followed by the next oldest, etc."
    ),
    WmlsCode.DUPLICATE_OBJECT: (
        "For WMLS_AddToStore, a data-object with the same type and unique identifier(s) "
        "must NOT already exist in the persistent store."
    ),
    WmlsCode.MISSING_PARENTAGE_UID: (
        "For WMLS_AddToStore, all parentage-pointers and lower level (child) uid values "
        "must be defined in the XMLin."
    ),
    WmlsCode.MISSING_WMLTYPE: "A non-empty value must be defined for WMLtypeIn.",
    WmlsCode.MISSING_INPUT_TEMPLATE: (
        "A non-empty value must be defined for the input template."
    ),
    WmlsCode.INPUT_TEMPLATE_NONCONFORMING: (
        "The input template must conform to the appropriate derived schema."
    ),
    WmlsCode.EMPTY_ELEMENT_NONCONFORMING: (
        "A template containing empty values must otherwise conform to the appropriate "
        "derived schema."
    ),
    WmlsCode.PARAMETERS_NOT_ENCODED: (
        "The OptionsIn parameter string must be encoded utilizing a subset of the "
        "encoding rules for HTML form content type application/x-www-form-urlencoded."
    ),
    WmlsCode.INPUT_OBJECT_NOT_COMPLIANT: (
        "The result of an add, update, or delete operation must be compliant with the "
        "derived write schema after performing a retrieval of the complete data-object."
    ),
    WmlsCode.OBJECT_NOT_SUPPORTED: (
        "The data-object must be supported by the server as defined in its capability "
        "data-object."
    ),
    WmlsCode.INSUFFICIENT_RIGHTS: (
        "In the server configuration for the site, the user must have rights to perform "
        "the requested operation on the data-object."
    ),
    WmlsCode.MISSING_UID: (
        "The input template must specify the unique identifiers of one data-object to "
        "be processed."
    ),
    WmlsCode.EMPTY_UID: (
        "For WMLS_DeleteFromStore, an empty uid attribute must not be specified."
    ),
    WmlsCode.EMPTY_UOM: (
        "For WMLS_DeleteFromStore, an empty uom attribute must not be specified."
    ),
    WmlsCode.INVALID_UOM: (
        "The value of the uom attribute is must match an 'annotation' attribute "
        "from the WITSML Units Dictionary XML file."
    ),
    WmlsCode.INVALID_RETURN_VALUE: (
        "For WMLS_GetBaseMsg, a non-empty value must be specified for ReturnValueIn."
    ),
    WmlsCode.DATA_VERSION_NOT_SUPPORTED: (
        "For WMLS_GetCap, the OptionsIn keyword 'dataVersion' must specify a Data Schema "
        "Version that is supported by the server as defined by WMLS_GetVersion."
    ),
    WmlsCode.MISSING_DATA_VERSION: (
        "For WMLS_GetCap, the OptionsIn keyword 'dataVersion' must be specified."
    ),
    WmlsCode.INVALID_OPTIONS_COMBINATION: (
        "The OptionsIn keyword 'requestObjectSelectionCapability' with a value "
        "other than 'none' must not be specified with any other OptionsIn keyword."
    ),
    WmlsCode.INVALID_MINIMUM_QUERY: (
        "If the OptionsIn keyword 'requestObjectSelectionCapability' is specified "
        "with a value other than 'none' then QueryIn must be the Minimum Query "
        "Template."
    ),
    WmlsCode.NOT_BOTTOM_LEVEL: (
        "If cascading deletes are not invoked, a client must only request deletion of "
        "bottom level data-objects such that all child data-objects are deleted before "
        "the parent is deleted."
    ),
    WmlsCode.OBJECT_NOT_EXIST: (
        "A data-object with the same type and unique identifier(s) must already exist in "
        "the persistent store."
    ),
    WmlsCode.INDEX_CURVE_NOT_FOUND: (
        "When updating data in a systematically growing data-object the indexCurve must "
        "be specified in the mnemonicList."
    ),
    WmlsCode.MAX_DATA_EXCEEDED: (
        "The client must not attempt to add or update more data than is allowed by the "
        "server's maxDataNodes and maxDataPoints values."
    ),
    WmlsCode.MISSING_UNIT_FOR_MEASURE: (
        "For WMLS_AddToStore and WMLS_UpdateInStore, the client must always specify "
        "the unit for all measure data."
    ),
    WmlsCode.API_VERSION_NOT_SUPPORTED: (
        "The server does not support the API Version provided by the client."
    ),
    WmlsCode.QUERY_NOT_SUPPORTED: "Query not supported.",
    WmlsCode.MISSING_PARENT: "Parent does not exist.",
    WmlsCode.ROW_DATA_COUNT: (
        "Number of data values per row does not match number of column-identifiers "
        "(mnemonics)."
    ),
    WmlsCode.INVALID_REQUEST_LATEST_VALUE: (
        "The value of the OptionsIn keyword of 'requestLatestValue' MUST be greater than "
        "zero and less than or equal to the MaxRequestLatestValue."
    ),
    WmlsCode.ERROR_ADDING: "Error adding data to data store.",
    WmlsCode.ERROR_READING: "Error reading data from data store.",
    WmlsCode.ERROR_UPDATING: "Error updating data in data store.",
    WmlsCode.ERROR_DELETING: "Error deleting data from data store.",
    WmlsCode.TRANSACTION_TIMEOUT: "Transaction timeout error.",
    WmlsCode.MAX_DOCUMENT_SIZE_EXCEEDED: "Max document size exceeded.",
}


def base_message(code: int) -> str:
    return BASE_MESSAGES.get(code, "Unknown error code.")

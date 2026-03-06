# DataZone Custom Model Files

## datazone-2018-05-10.json

This custom DataZone service model file is **required** for MLflow connection support.

### Purpose

The public boto3 DataZone client (as of boto3 1.42.60+) does not include support for the `MLFLOW` connection type. This custom model file extends the DataZone API to include:

- `MLFLOW` connection type in the `ConnectionType` enum
- `mlflowProperties` for connection input, output, and patch operations
- `MlflowPropertiesInput`, `MlflowPropertiesOutput`, and `MlflowPropertiesPatch` shapes

### Usage

The `ConnectionCreator._get_custom_datazone_client()` method loads this model file to create a boto3 client that supports MLflow connections. This is only used when creating or managing connections of type `MLFLOW`.

### Migration Note

This file was retained during the migration from `datazone-internal` to the public DataZone client. The internal client model file (`datazone-internal-2018-05-10.json`) was removed as it's no longer needed, but this file remains necessary for MLflow functionality.

### Future Considerations

If AWS adds native MLflow connection support to the public DataZone API in a future boto3 release, this custom model file can be removed and the code can be updated to use the standard client for all connection types.

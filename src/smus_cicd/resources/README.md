# DataZone Custom Model Files

This directory previously contained custom DataZone service model files used to
extend the boto3 DataZone client with additional connection type support.

## Removed Files

### datazone-internal-2018-05-10.json (removed)

Was used for the internal DataZone client. Removed as part of the migration to
the public DataZone API.

### datazone-2018-05-10.json (removed)

Was used to add MLflow connection support (`MLFLOW` connection type and
`mlflowProperties` shapes) before the public boto3 DataZone client included
native support. As of boto3 1.42.60+, the public client natively supports
MLflow connections, so this custom model is no longer needed.

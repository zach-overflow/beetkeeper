# `beetkeeper-api-client`

A Python client for the [beetkeeper](https://beetkeeper.dadbodaudio.com/) REST API, generated from the
server's OpenAPI spec. Every endpoint has an `async` method and a blocking `_sync` variant.

```python
from beetkeeper_api_client import ApiClient, Configuration, MonitoringApi

config = Configuration(host="http://localhost:8337", access_token="<api token>")
health = MonitoringApi(ApiClient(config)).health_api_health_get_sync()
```

## Official User Reference

Go to https://beetkeeper.dadbodaudio.com/ for all official `beetkeeper` user guides and docs.

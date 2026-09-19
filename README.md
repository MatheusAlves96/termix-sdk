# termix-sdk

Python client SDK for the Termix REST API.

## Documentation

- [Generating our own Termix API spec](tools/spec-gen/docs/spec-generation-strategy.md): why the SDK does not rely on the official `openapi.json`, and how the spec is derived from the Termix backend source (route discovery, auth, typed request bodies, every response per status code, Drizzle schema, test examples).

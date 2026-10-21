# BeaconDesk: API keys and request limits

Owners and administrators create API keys in Settings > Developer > API keys.
Each key belongs to one workspace. Select the smallest set of permissions
needed for the integration. The key value is shown only once.

Store API keys on your server, never in browser JavaScript or public source
repositories. To replace a leaked key, create a replacement, update your
integration, and revoke the old key from the API keys page.

The fictional BeaconDesk API permits sixty requests per minute per key.
When the limit is reached, it returns HTTP 429 and a Retry-After header
containing the wait time in seconds. Wait for that duration before retrying.
These limits describe BeaconDesk's example API, not OriginChainDB.

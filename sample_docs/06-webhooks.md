# BeaconDesk: webhook delivery

Create a webhook from Settings > Developer > Webhooks. Enter an HTTPS endpoint
and select task.created, task.updated, or task.completed events.
Webhook payloads contain an event_id, event_type, workspace_id, and task_id.

The receiver should return a successful HTTP response within five seconds.
If delivery fails, BeaconDesk retries after one minute, five minutes, and
thirty minutes. After those three retries, the event is marked failed.

Webhook delivery is at least once. Use event_id to deduplicate repeated
deliveries. Failed deliveries can be inspected from the webhook's Delivery
history tab. A workspace administrator can request a manual retry there.

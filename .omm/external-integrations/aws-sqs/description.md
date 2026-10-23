SQS standard queues for shard messages and dead letters. The API sends batches; Lambda's event source mapping receives and deletes; the worker calls ChangeMessageVisibility to shorten retry waits.

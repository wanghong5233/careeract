#!/bin/sh
set -eu

TEMPORAL_ADDRESS=${TEMPORAL_ADDRESS:-temporal:7233}
TEMPORAL_NAMESPACE=${TEMPORAL_NAMESPACE:-default}

until temporal operator cluster health --address "$TEMPORAL_ADDRESS"; do
  sleep 2
done

if ! temporal operator namespace describe \
  --address "$TEMPORAL_ADDRESS" \
  --namespace "$TEMPORAL_NAMESPACE" >/dev/null 2>&1; then
  temporal operator namespace create \
    --address "$TEMPORAL_ADDRESS" \
    --namespace "$TEMPORAL_NAMESPACE"
fi

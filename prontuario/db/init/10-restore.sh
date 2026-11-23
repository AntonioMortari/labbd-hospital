#!/bin/sh
# Roda uma única vez, na primeira criação do volume: restaura o backup entregue (prontuario_medico.zip) no MongoDB.
mongorestore --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" \
  --authenticationDatabase admin --db prontuario_medico /dump/prontuario_medico

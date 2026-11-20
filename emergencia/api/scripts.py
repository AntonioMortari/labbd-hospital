# Chamar o próximo da fila: retira, marca como chamado e publica no painel, tudo numa operação.
CALL_NEXT = """
local r = redis.call('ZPOPMIN', KEYS[1])
if #r == 0 then return nil end
local pid = r[1]
local pkey = 'patient:' .. pid
redis.call('HSET', pkey, 'status', 'chamado', 'room', ARGV[1], 'called_at', ARGV[2])
local payload = cjson.encode({
  type = 'call',
  patient = pid,
  name = redis.call('HGET', pkey, 'name'),
  priority = redis.call('HGET', pkey, 'priority'),
  room = ARGV[1]
})
redis.call('LPUSH', KEYS[2], payload)
redis.call('LTRIM', KEYS[2], 0, 19)
redis.call('PUBLISH', KEYS[3], payload)
return payload
"""

# Alocar leito: só uma chamada concorrente consegue passar de 'livre' para 'ocupado'.
# Retornos: 1 ok | 0 leito ocupado | -1 leito inexistente | -2 paciente inexistente | -3 paciente já tem leito
ALLOCATE_BED = """
local st = redis.call('HGET', KEYS[1], 'status')
if st == false then return -1 end
if st ~= 'livre' then return 0 end
if redis.call('EXISTS', KEYS[2]) == 0 then return -2 end
if redis.call('HEXISTS', KEYS[2], 'bed') == 1 then return -3 end
redis.call('HSET', KEYS[1], 'status', 'ocupado', 'patient', ARGV[2], 'since', ARGV[3])
redis.call('HSET', KEYS[2], 'bed', ARGV[1], 'status', 'internado')
redis.call('ZREM', 'triage:queue', ARGV[2])
redis.call('SMOVE', 'beds:free', 'beds:occupied', ARGV[1])
redis.call('PUBLISH', KEYS[3], cjson.encode({
  type = 'bed', bed = ARGV[1], status = 'ocupado', patient = ARGV[2],
  free = redis.call('SCARD', 'beds:free')
}))
return 1
"""

# Liberar leito
RELEASE_BED = """
local pid = redis.call('HGET', KEYS[1], 'patient')
if pid == false then return 0 end
redis.call('HSET', KEYS[1], 'status', 'livre')
redis.call('HDEL', KEYS[1], 'patient', 'since')
redis.call('HDEL', 'patient:' .. pid, 'bed')
redis.call('HSET', 'patient:' .. pid, 'status', 'alta')
redis.call('SMOVE', 'beds:occupied', 'beds:free', ARGV[1])
redis.call('PUBLISH', KEYS[2], cjson.encode({
  type = 'bed', bed = ARGV[1], status = 'livre',
  free = redis.call('SCARD', 'beds:free')
}))
return 1
"""

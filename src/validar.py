"""Validador mínimo de JSON Schema (subconjunto), sem dependências externas.

Suporta: type (um ou lista), required, properties, items, enum, minimum, maximum, minLength,
minItems, pattern, additionalProperties (booleano) e patternProperties não. Os arquivos em schemas/
são JSON Schema padrão, então também funcionam com a biblioteca `jsonschema` se preferir.
"""
import re

TIPOS = {
    'string': lambda v: isinstance(v, str),
    'number': lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    'integer': lambda v: isinstance(v, int) and not isinstance(v, bool),
    'boolean': lambda v: isinstance(v, bool),
    'array': lambda v: isinstance(v, list),
    'object': lambda v: isinstance(v, dict),
    'null': lambda v: v is None,
}


def validar(dado, schema, caminho='$'):
    """Devolve a lista de erros (strings com o caminho do campo). Lista vazia = válido."""
    erros = []
    t = schema.get('type')
    if t is not None:
        ts = t if isinstance(t, list) else [t]
        if not any(TIPOS[x](dado) for x in ts):
            return [f'{caminho}: esperado {"/".join(ts)}, encontrado {type(dado).__name__} ({str(dado)[:40]!r})']
    if 'enum' in schema and dado not in schema['enum']:
        erros.append(f'{caminho}: valor {dado!r} fora de {schema["enum"]}')
    if isinstance(dado, (int, float)) and not isinstance(dado, bool):
        if 'minimum' in schema and dado < schema['minimum']:
            erros.append(f'{caminho}: {dado} abaixo do mínimo {schema["minimum"]}')
        if 'maximum' in schema and dado > schema['maximum']:
            erros.append(f'{caminho}: {dado} acima do máximo {schema["maximum"]}')
    if isinstance(dado, str):
        if 'minLength' in schema and len(dado) < schema['minLength']:
            erros.append(f'{caminho}: texto vazio ou curto demais')
        if 'pattern' in schema and not re.search(schema['pattern'], dado):
            erros.append(f'{caminho}: {dado!r} não casa com {schema["pattern"]}')
    if isinstance(dado, dict):
        for k in schema.get('required', []):
            if k not in dado:
                erros.append(f'{caminho}: campo obrigatório ausente: {k}')
        props = schema.get('properties', {})
        for k, v in dado.items():
            if k in props:
                erros += validar(v, props[k], f'{caminho}.{k}')
            elif schema.get('additionalProperties') is False:
                erros.append(f'{caminho}: campo não previsto: {k}')
            elif isinstance(schema.get('additionalProperties'), dict):
                erros += validar(v, schema['additionalProperties'], f'{caminho}.{k}')
    if isinstance(dado, list):
        if 'minItems' in schema and len(dado) < schema['minItems']:
            erros.append(f'{caminho}: {len(dado)} itens, mínimo {schema["minItems"]}')
        if 'items' in schema:
            for i, it in enumerate(dado):
                erros += validar(it, schema['items'], f'{caminho}[{i}]')
    return erros

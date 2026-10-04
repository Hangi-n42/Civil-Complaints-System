"""Bounded endpoint membership judgment shared by diagnostic and product calls."""
PROMPT = '''제공 원문과 후보만 사용하여 요청된 관계의 유형 연결을 검수한다. 원명제의 끝점 대상이 선택 유형의 정의·조건·예외에 속하는지를 판단한다. 개념 동치가 필요한 것은 아니다. 업무 연관·소유·부분과 전체 관계만으로 유형 포함을 지지하지 않는다. 끝점 표현이 가리키는 중심 대상의 종류와 선택 유형의 종류를 먼저 대조한다. 어떤 유형을 이용·관리하거나 그곳에 거주하는 대상은 그 유형 자체의 하위 유형이 아니다. 유형 포함 판정은 그 대상을 다른 것으로 바꾸지 않은 is-a여야 한다. 더 넓은 유형은 원명제의 좁은 한정이 보존되면 가능하며, 근거 없이 더 좁은 유형으로 대상 일부를 제외하면 부적합하다.
각 끝점의 실제 표현·조건과 선택 유형 정의를 대조하여 supported/refuted/unknown과 구체적인 이유를 각각 반환한다. 판정에 필요한 정의·한정이 실제 부족하면 unknown이다. 법정 정의 문구가 없다는 이유만으로 원문에 근거한 역할 추상화를 보류하지 않는다. 자료의 인접 조항은 서로 다른 정의일 수 있으므로 해당 대상의 구간을 대조한다.
relation_bindings는 검수 대상 선택이며 정답이 아니다. source_relation 없는 평가 조합에서는 endpoint_labels가 있으면 그 표현을 사용하고, 없으면 자연어 subject/object 끝점 필드를 사용한다. 요청된 끝점만 판단하며 원명제 수정·누락 발굴·새 유형 설계·전체 의미 검수를 수행하지 않는다. JSON schema에 지정된 candidate_ref, binding_checks, binding_reasons, 실제 제공 source_refs만 반환한다. 이유는 각 400자 이내이며 원문과 유형 정의의 대응 또는 충돌을 설명한다.'''


def schema(identifier, endpoints, source_refs):
    return dict(type='object',additionalProperties=False,required=['candidate_ref','binding_checks','binding_reasons','source_refs'],
        properties=dict(candidate_ref=dict(type='string',enum=[identifier]),
            binding_checks=dict(type='object',additionalProperties=False,required=endpoints,
                properties={k:dict(type='string',enum=['supported','refuted','unknown']) for k in endpoints}),
            binding_reasons=dict(type='object',additionalProperties=False,required=endpoints,
                properties={k:dict(type='string',minLength=1,maxLength=400) for k in endpoints}),
            source_refs=dict(type='array',minItems=1,uniqueItems=True,items=dict(type='string',enum=source_refs))))


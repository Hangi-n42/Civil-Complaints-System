import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it, vi } from 'vitest';
vi.mock('@/lib/knowledgeReview',()=>import('../lib/knowledgeReview'));
import KnowledgeDiscoveryStart from '../components/KnowledgeDiscoveryStart';
import KnowledgeHumanCost from '../components/KnowledgeHumanCost';
it('자료 고정과 질문 없이 분석을 시작하지 않고 기본 화면에 JSON 입력을 요구하지 않는다',()=>{
  const html=renderToStaticMarkup(createElement(KnowledgeDiscoveryStart,{request:async()=>{throw Error('unexpected');},onReady:()=>{},disabled:false}));
  expect(html).toContain('선택 자료 고정');expect(html).toContain('한 줄에 하나');expect(html).toContain('disabled=""');expect(html).not.toContain('(JSON)');
});
it('실제 참가·비용 미측정은 총 시간을 0으로 표시하지 않는다',()=>{
  const html=renderToStaticMarkup(createElement(KnowledgeHumanCost,{run:null,change:null}));
  expect(html).toContain('필수 비용 미측정 · 계산하지 않음');expect(html).toContain('모델 대기·휴식');expect(html).toContain('교육');expect(html).toContain('민원 적용');
});

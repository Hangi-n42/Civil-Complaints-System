"""
민원 원천 데이터 파싱 스크립트

raw_data의 JSON 파일들을 읽어서 consulting_content를 
제목(title), 민원인 질문(Q), 상담사 답변(A)으로 파싱합니다.

사용법:
    python parse_consulting_data.py --input data/raw_data --output data/processed
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ConsultingData:
    """파싱된 민원 데이터"""
    source_id: str
    source: str
    consulting_date: str  # YYYY-MM-DD 형식으로 변환
    consulting_category: str
    title: str
    client_question: str
    consultant_answer: str
    consulting_turns: int
    original_length: int
    parsing_success: bool
    parsing_error: Optional[str] = None


class ConsultingContentParser:
    """consulting_content 파싱 클래스"""
    
    # 구분자 정규식 (공백 불감)
    PATTERN_TITLE = re.compile(r'제목\s*:\s*(.+?)(?=\n|^Q)', re.MULTILINE)
    PATTERN_Q = re.compile(r'^Q\s*:\s*(.+?)(?=^A\s*:)', re.MULTILINE | re.DOTALL)
    PATTERN_A = re.compile(r'^A\s*:\s*(.+)$', re.MULTILINE | re.DOTALL)
    
    @staticmethod
    def clean_encoded_linebreaks(text: str) -> str:
        """Windows 인코딩 문자 제거 (경상북도 파일)"""
        text = text.replace('_x000D_\n', '\n')
        text = text.replace('_x000D_', '')
        return text
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """텍스트 정제"""
        if not text:
            return ""
        
        # 앞뒤 공백 제거
        text = text.strip()
        
        # 혼재된 개행 문자 통일
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # 다중 줄바꿈 → 단일 줄바꿈
        text = re.sub(r'\n\n+', '\n', text)
        
        # 내부 연속 공백 정규화
        text = re.sub(r'  +', ' ', text)
        
        return text
    
    def parse(self, content: str) -> Dict[str, str]:
        """
        consulting_content를 파싱해서 제목, Q, A로 분리
        
        Args:
            content: consulting_content 문자열
            
        Returns:
            {
                'title': 제목,
                'client_question': 민원인 질문,
                'consultant_answer': 상담사 답변
            }
        """
        try:
            # Step 1: 특수 인코딩 문자 제거
            content = self.clean_encoded_linebreaks(content)
            
            # Step 2: 제목 추출
            title_match = self.PATTERN_TITLE.search(content)
            title = title_match.group(1).strip() if title_match else "제목없음"
            
            # Step 3: Q(민원인 질문) 추출
            q_match = self.PATTERN_Q.search(content)
            client_question = q_match.group(1).strip() if q_match else ""
            
            # Step 4: A(상담사 답변) 추출
            a_match = self.PATTERN_A.search(content)
            consultant_answer = a_match.group(1).strip() if a_match else ""
            
            return {
                'title': self.normalize_text(title),
                'client_question': self.normalize_text(client_question),
                'consultant_answer': self.normalize_text(consultant_answer)
            }
            
        except Exception as e:
            logger.error(f"Parse error: {e}")
            return {
                'title': "파싱실패",
                'client_question': self.normalize_text(content),
                'consultant_answer': ""
            }


class ConsultingDataProcessor:
    """민원 데이터 처리 클래스"""
    
    def __init__(self):
        self.parser = ConsultingContentParser()
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'by_source': {}
        }
    
    def format_date(self, date_str: str) -> str:
        """YYYYMMDD → YYYY-MM-DD 형식 변환"""
        try:
            if not date_str or len(date_str) != 8:
                return date_str
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        except Exception as e:
            logger.warning(f"Date formatting error: {date_str} - {e}")
            return date_str
    
    def normalize_category(self, category: str) -> str:
        """카테고리 정규화"""
        if not category or category.strip() == "":
            return "미분류"
        return category.strip()
    
    def process_record(self, raw_record: dict) -> ConsultingData:
        """단일 레코드 처리"""
        try:
            # 필수 필드 검증
            if not raw_record.get('consulting_content'):
                raise ValueError("consulting_content is empty")
            
            # consulting_content 파싱
            parsed = self.parser.parse(raw_record['consulting_content'])
            
            # ConsultingData 객체 생성
            data = ConsultingData(
                source_id=raw_record.get('source_id', ''),
                source=raw_record.get('source', ''),
                consulting_date=self.format_date(raw_record.get('consulting_date', '')),
                consulting_category=self.normalize_category(
                    raw_record.get('consulting_category', '')
                ),
                title=parsed['title'],
                client_question=parsed['client_question'],
                consultant_answer=parsed['consultant_answer'],
                consulting_turns=int(raw_record.get('consulting_turns', 0)),
                original_length=int(raw_record.get('consulting_length', 0)),
                parsing_success=True
            )
            
            # 통계 업데이트
            self.stats['success'] += 1
            source = data.source
            if source not in self.stats['by_source']:
                self.stats['by_source'][source] = {'success': 0, 'failed': 0}
            self.stats['by_source'][source]['success'] += 1
            
            return data
            
        except Exception as e:
            # 실패 처리
            logger.warning(f"Processing error for {raw_record.get('source_id')}: {e}")
            self.stats['failed'] += 1
            source = raw_record.get('source', 'unknown')
            if source not in self.stats['by_source']:
                self.stats['by_source'][source] = {'success': 0, 'failed': 0}
            self.stats['by_source'][source]['failed'] += 1
            
            return ConsultingData(
                source_id=raw_record.get('source_id', ''),
                source=raw_record.get('source', ''),
                consulting_date=self.format_date(raw_record.get('consulting_date', '')),
                consulting_category=self.normalize_category(
                    raw_record.get('consulting_category', '')
                ),
                title="처리실패",
                client_question="",
                consultant_answer="",
                consulting_turns=0,
                original_length=0,
                parsing_success=False,
                parsing_error=str(e)
            )
    
    def process_file(self, file_path: Path) -> List[ConsultingData]:
        """JSON 파일 처리"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            
            if not isinstance(raw_data, list):
                logger.error(f"Invalid JSON structure in {file_path}")
                return []
            
            results = []
            for record in raw_data:
                self.stats['total'] += 1
                result = self.process_record(record)
                results.append(result)
            
            logger.info(f"Processed {len(raw_data)} records from {file_path.name}")
            return results
            
        except Exception as e:
            logger.error(f"File processing error for {file_path}: {e}")
            return []
    
    def process_directory(self, input_dir: Path) -> List[ConsultingData]:
        """디렉토리의 모든 JSON 파일 처리"""
        all_results = []
        json_files = sorted(input_dir.glob('*.json'))
        
        logger.info(f"Found {len(json_files)} JSON files in {input_dir}")
        
        for file_path in json_files:
            results = self.process_file(file_path)
            all_results.extend(results)
        
        return all_results
    
    def print_stats(self):
        """통계 출력"""
        print("\n" + "="*60)
        print("처리 결과 통계")
        print("="*60)
        print(f"총 건수: {self.stats['total']}")
        print(f"성공: {self.stats['success']}")
        print(f"실패: {self.stats['failed']}")
        print(f"성공률: {self.stats['success']/max(1, self.stats['total'])*100:.1f}%")
        
        print("\n지역별 통계:")
        for source, counts in sorted(self.stats['by_source'].items()):
            total = counts['success'] + counts['failed']
            print(f"  {source}: {counts['success']}/{total} 성공")
        print("="*60 + "\n")


def save_results(results: List[ConsultingData], output_dir: Path):
    """결과 저장"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # JSON 저장
    json_output = output_dir / 'processed_consulting_data.json'
    with open(json_output, 'w', encoding='utf-8') as f:
        json.dump(
            [asdict(r) for r in results],
            f,
            ensure_ascii=False,
            indent=2
        )
    logger.info(f"Saved JSON output to {json_output}")
    
    # CSV 저장 (선택사항)
    try:
        import csv
        csv_output = output_dir / 'processed_consulting_data.csv'
        
        if results:
            with open(csv_output, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=asdict(results[0]).keys())
                writer.writeheader()
                writer.writerows([asdict(r) for r in results])
            logger.info(f"Saved CSV output to {csv_output}")
    except ImportError:
        logger.warning("CSV module not available, skipping CSV output")
    
    # 실패 항목 별도 저장
    failed_results = [r for r in results if not r.parsing_success]
    if failed_results:
        error_output = output_dir / 'failed_records.json'
        with open(error_output, 'w', encoding='utf-8') as f:
            json.dump(
                [asdict(r) for r in failed_results],
                f,
                ensure_ascii=False,
                indent=2
            )
        logger.info(f"Saved {len(failed_results)} failed records to {error_output}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='민원 원천 데이터 파싱 및 처리'
    )
    parser.add_argument(
        '--input',
        type=Path,
        default=Path('data/raw_data'),
        help='입력 디렉토리 (기본값: data/raw_data)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('data/processed'),
        help='출력 디렉토리 (기본값: data/processed)'
    )
    
    args = parser.parse_args()
    
    # 입력 디렉토리 검증
    if not args.input.exists():
        logger.error(f"Input directory not found: {args.input}")
        return
    
    # 처리
    processor = ConsultingDataProcessor()
    results = processor.process_directory(args.input)
    
    # 통계 출력
    processor.print_stats()
    
    # 결과 저장
    save_results(results, args.output)
    
    # 샘플 출력
    if results:
        print("\n샘플 출력 (첫 3개 성공 항목):")
        print("="*60)
        success_results = [r for r in results if r.parsing_success][:3]
        for result in success_results:
            print(f"\n[{result.source}] {result.source_id}")
            print(f"날짜: {result.consulting_date}")
            print(f"카테고리: {result.consulting_category}")
            print(f"제목: {result.title[:80]}")
            print(f"민원인(Q): {result.client_question[:80]}...")
            print(f"상담사(A): {result.consultant_answer[:80]}...")
        print("="*60)


if __name__ == '__main__':
    main()

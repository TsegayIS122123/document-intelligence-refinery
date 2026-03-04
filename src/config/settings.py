"""
Load configuration from extraction_rules.yaml
"""

import yaml
from pathlib import Path
from typing import Dict, Any,Optional


class Settings:
    """Load and manage configuration"""
    
    def __init__(self):
        self.rules = {}
    
    def load_rules(self, config_path: Optional[Path] = None) -> Dict[str, Any]:
        """Load extraction rules from YAML"""
        if config_path is None:
            config_path = Path("rubric/extraction_rules.yaml")
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                self.rules = yaml.safe_load(f)
        else:
            # Default rules based on your Phase 0 analysis
            self.rules = {
                'classification': {
                    'character_density': {
                        'scanned_max_chars': 50,
                        'digital_min_chars': 100,
                        'mixed_range': [50, 100]
                    },
                    'image_ratio': {
                        'scanned_min_ratio': 0.5,
                        'digital_max_ratio': 0.3
                    }
                },
                'confidence': {
                    'fast_text': {'min_confidence': 0.7},
                    'layout_aware': {'min_confidence': 0.8},
                    'vision': {'min_confidence': 0.9}
                },
                'sampling': {
                    'initial_analysis_pages': 5
                }
            }
        
        return self.rules


settings = Settings()
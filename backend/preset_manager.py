#!/usr/bin/env python3
"""
SuperElite 预设管理模块
管理用户配置预设
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict


@dataclass
class Preset:
    """预设配置"""
    name: str
    description: str = ""
    thresholds: tuple = (78.0, 72.0, 66.0, 58.0)
    quality_weight: float = 0.4
    aesthetic_weight: float = 0.6
    write_xmp: bool = True
    organize: bool = False
    is_builtin: bool = False
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        d = asdict(self)
        d['thresholds'] = list(self.thresholds)
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Preset':
        """从字典创建"""
        data = data.copy()
        if 'thresholds' in data:
            data['thresholds'] = tuple(data['thresholds'])
        return cls(**data)


# 内置预设
BUILTIN_PRESETS = {
    "default": Preset(
        name="default",
        description="默认设置 - 适中筛选",
        thresholds=(78.0, 72.0, 66.0, 58.0),
        is_builtin=True,
    ),
    "strict": Preset(
        name="strict",
        description="严格筛选 - 只保留精品",
        thresholds=(85.0, 80.0, 75.0, 70.0),
        is_builtin=True,
    ),
    "relaxed": Preset(
        name="relaxed",
        description="宽松筛选 - 保留更多照片",
        thresholds=(70.0, 60.0, 50.0, 40.0),
        is_builtin=True,
    ),
}


class PresetManager:
    """预设管理器"""
    
    def __init__(self, presets_dir: Optional[str] = None):
        """
        初始化预设管理器
        
        Args:
            presets_dir: 预设目录，默认 ~/.superelite/presets/
        """
        if presets_dir:
            self.presets_dir = Path(presets_dir)
        else:
            self.presets_dir = Path.home() / ".superelite" / "presets"
        
        self.presets_dir.mkdir(parents=True, exist_ok=True)
        
        # 用户预设文件路径
        self.user_preset_path = self.presets_dir / "user.json"
    
    def list_presets(self) -> List[Dict]:
        """
        列出所有可用预设
        
        Returns:
            预设信息列表
        """
        presets = []
        
        # 内置预设
        for name, preset in BUILTIN_PRESETS.items():
            presets.append({
                "name": name,
                "description": preset.description,
                "is_builtin": True,
            })
        
        # 用户预设
        if self.user_preset_path.exists():
            presets.append({
                "name": "user",
                "description": "用户自定义设置",
                "is_builtin": False,
            })
        
        # 其他自定义预设
        for f in self.presets_dir.glob("*.json"):
            if f.stem not in ["user"] + list(BUILTIN_PRESETS.keys()):
                try:
                    data = json.loads(f.read_text(encoding='utf-8'))
                    presets.append({
                        "name": f.stem,
                        "description": data.get("description", ""),
                        "is_builtin": False,
                    })
                except:
                    pass
        
        return presets
    
    def get_preset(self, name: str) -> Optional[Preset]:
        """
        获取预设
        
        Args:
            name: 预设名称
            
        Returns:
            预设对象，不存在返回 None
        """
        # 内置预设
        if name in BUILTIN_PRESETS:
            return BUILTIN_PRESETS[name]
        
        # 用户预设或自定义预设
        preset_path = self.presets_dir / f"{name}.json"
        if preset_path.exists():
            try:
                data = json.loads(preset_path.read_text(encoding='utf-8'))
                data['name'] = name
                data['is_builtin'] = False
                return Preset.from_dict(data)
            except Exception as e:
                print(f"⚠️  加载预设失败: {e}")
                return None
        
        return None
    
    def save_preset(self, preset: Preset) -> bool:
        """
        保存预设
        
        Args:
            preset: 预设对象
            
        Returns:
            是否保存成功
        """
        if preset.name in BUILTIN_PRESETS:
            print(f"❌ 无法覆盖内置预设: {preset.name}")
            return False
        
        preset_path = self.presets_dir / f"{preset.name}.json"
        
        try:
            data = preset.to_dict()
            del data['name']  # 名称由文件名决定
            del data['is_builtin']
            
            preset_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            return True
        except Exception as e:
            print(f"❌ 保存预设失败: {e}")
            return False
    
    def save_user_preset(
        self,
        thresholds: tuple,
        quality_weight: float = 0.4,
        aesthetic_weight: float = 0.6,
        write_xmp: bool = True,
        organize: bool = False,
    ) -> bool:
        """
        保存用户预设
        
        快捷方法，保存到 user.json
        """
        preset = Preset(
            name="user",
            description="用户自定义设置",
            thresholds=thresholds,
            quality_weight=quality_weight,
            aesthetic_weight=aesthetic_weight,
            write_xmp=write_xmp,
            organize=organize,
        )
        return self.save_preset(preset)
    
    def get_user_preset(self) -> Optional[Preset]:
        """获取用户预设"""
        return self.get_preset("user")
    
    def delete_preset(self, name: str) -> bool:
        """
        删除预设
        
        Args:
            name: 预设名称
            
        Returns:
            是否删除成功
        """
        if name in BUILTIN_PRESETS:
            print(f"❌ 无法删除内置预设: {name}")
            return False
        
        preset_path = self.presets_dir / f"{name}.json"
        if preset_path.exists():
            preset_path.unlink()
            return True
        
        return False
    
    def print_presets(self):
        """打印所有预设列表"""
        presets = self.list_presets()
        
        print("\n" + "=" * 50)
        print("  可用预设")
        print("=" * 50)
        
        for p in presets:
            tag = "[内置]" if p["is_builtin"] else "[用户]"
            print(f"  {tag} {p['name']:<12} - {p['description']}")
        
        print()


# 全局实例
_manager = None


def get_preset_manager() -> PresetManager:
    """获取全局预设管理器"""
    global _manager
    if _manager is None:
        _manager = PresetManager()
    return _manager

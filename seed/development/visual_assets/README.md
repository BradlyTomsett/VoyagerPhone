# V14.38 图片索引（不包含图像）

本次游戏存档**只包含** image_source_index.json 与图片来源闸门.py，以及文字操作说明。所有图片原图及五个图片ZIP均不装入游戏存档。

在项目「来源」中保留并单独提供：
- vehicle_posters_en.zip
- combat_robot_posters_en.zip
- space_uav_posters_en.zip
- armored_vehicle_posters_en.zip
- combat_uav_armored_images_en.zip

图片索引记录ZIP文件名、ZIP整体SHA-256、包内PNG成员名、图片SHA-256与中文名称别名。

用法（有原始来源ZIP时）：
```bash
python development/visual_assets/舰队图片来源闸门.py index-check
python development/visual_assets/舰队图片来源闸门.py --root /mnt/data verify-all
python development/visual_assets/舰队图片来源闸门.py --root /mnt/data resolve 林舟-4
python guard.py --check
python guard.py --image-resolve 岩途-5 --image-source-dir /mnt/data
```

没有挂载来源图包时，游戏存档完整性检查与恢复仍能继续，但已有装备的配图操作须中止，**不允许使用生成图或搜索图冒充原始图片**。这项检查程序不能拦截聊天模型不执行工具直接出图的行为，仍需回复前实际运行校验。

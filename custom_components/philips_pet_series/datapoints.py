"""
Datapoints
"""

datapoints = {
    "106": {
        "dpCode": "motion_sensitivity",
        "standardType": "Enum",
        "valueRange": ["0", "1", "2"],
        "niceNames": ["Low", "Medium", "High"],
        "path": "tuya_status",
    },
    "108": {
        "dpCode": "nightvision",
        "standardType": "Enum",
        "valueRange": ["0", "1", "2"],
        "niceNames": ["Auto", "Off", "Always On"],
        "path": "tuya_status",
    },
    "188": {
        "dpCode": "anti_flicker",
        "standardType": "Enum",
        "valueRange": ["0", "1", "2"],
        "niceNames": ["0", "1", "2"],
        "path": "tuya_status",
    },
    "201": {
        "dpCode": "feed_num",
        "standardType": "Integer",
        "properties": {"unit": "portions", "max": 20, "min": 0, "scale": 0, "step": 1, "mode": "box"},
        "path": "tuya_status"
    },
    "202": {
        "dpCode": "food_weight",
        "standardType": "Integer",
        "properties": {"unit": "g", "max": 100, "min": 1, "scale": 1, "step": 1, "mode": "slider"},
        "path": "tuya_status",
    },
    "231": {
        "dpCode": "device_volume",
        "standardType": "Integer",
        "properties": {"unit": "%", "min": 1, "max": 100, "scale": 1, "step": 1, "mode": "slider"},
        "path": "tuya_status",
    },
    "255": {
        "dpCode": "feed_abnormal",
        "standardType": "Integer",
        "properties": {"unit": "portions", "max": 255, "min": 0, "scale": 0, "step": 1, "mode": "box"},
        "path": "tuya_status",
    },
    "power": {
        "dpCode": "device_active",
        "standardType": "Boolean",
        "path": "",
    },
    "motion_notifications": {
        "dpCode": "push_notification_motion",
        "standardType": "Boolean",
        "path": "",
    },
}

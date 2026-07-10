import cv2

video_path = r"D:/Code/software_cup/software_cup/assets/avatar_idle.mp4"

cap = cv2.VideoCapture(video_path)

# 如果第一帧不好，可以跳到第 1 秒
cap.set(cv2.CAP_PROP_POS_MSEC, 1700)

ret, frame = cap.read()
cap.release()

if not ret:
    print("读取视频失败")
    exit()

roi = cv2.selectROI("select face area", frame, False, False)
cv2.destroyAllWindows()

x, y, w, h = roi

print("x =", x)
print("y =", y)
print("w =", w)
print("h =", h)
print("Wav2Lip --box 参数：")
print(f"--box {y} {y+h} {x} {x+w}")
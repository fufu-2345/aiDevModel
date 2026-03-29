# 1. เลือก Base Image เป็น Node.js (alpine คือเวอร์ชันที่เบาและทำงานไว)
FROM node:18-alpine

# 2. ตั้งค่าโฟลเดอร์ทำงานข้างใน Container ชื่อว่า /app
WORKDIR /app

# 3. ก๊อปปี้ไฟล์ package.json เข้าไปก่อน เพื่อเตรียมลง Library
COPY package*.json ./

# 4. สั่งติดตั้ง Library ทั้งหมด
RUN npm install

# 5. ก๊อปปี้ไฟล์โค้ดที่เหลือทั้งหมดในโปรเจคตามเข้าไป
COPY . .

# 6. เปิดพอร์ต (สมมติว่าแอปคุณรันพอร์ต 8080)
EXPOSE 8080

# 7. คำสั่งรันโปรเจค
CMD ["npm", "start"]
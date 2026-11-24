FROM nginx:1.27-alpine
COPY nginx.conf /usr/share/nginx.conf-template
RUN mv /usr/share/nginx.conf-template /etc/nginx/conf.d/default.conf
COPY public/ /usr/share/nginx/html/
EXPOSE 80

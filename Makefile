build:
	docker build -t hexlet/slackonar:latest .

save:
	docker run --rm -v $(CURDIR):/slackonar --env-file ./.env -it hexlet/slackonar:latest $(first) $(last)
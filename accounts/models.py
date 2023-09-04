import os
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser, User
from django.core.validators import RegexValidator
from django.db import models
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFill


class User(AbstractUser):
    followings = models.ManyToManyField(
        "self", related_name="followers", symmetrical=False
    )
    address = models.CharField(max_length=100)
    first_name = models.CharField(max_length=100, blank=True, unique=True)
    email = models.EmailField(unique=True)

    def profile_image_path(instance, filename):
        return f"profile/{instance.username}/{filename}"

    image = ProcessedImageField(upload_to=profile_image_path, blank=True, null=True)

    is_seller = models.BooleanField(default=False)
    phoneNumberRegex = RegexValidator(regex=r"^0[1-9]\d{0,2}-\d{3,4}-\d{4}$")
    phone = models.CharField(validators=[phoneNumberRegex], max_length=14)
    points = models.IntegerField(default=0)  # 현재 포인트
    total_points = models.IntegerField(default=0)  # 누적 포인트

    # 포인트 1년마다 초기화
    def reset_points_if_needed(self):
        one_year_ago = datetime.now().date() - timedelta(days=365)
        if self.last_login.date() < one_year_ago:
            self.points = 0

    def points_save(self, *args, **kwargs):
        self.reset_points_if_needed()
        super().save(*args, **kwargs)

    # 포인트 기부하면 기존의 포인트에서 빼기
    # def subtract_points(self, amount):
    #     self.points -= amount
    #     self.save()

    def delete(self, *args, **kargs):
        if self.image:
            os.remove(os.path.join(settings.MEDIA_ROOT, self.image.path))
        super(User, self).delete(*args, **kargs)

    def save(self, *args, **kwargs):
        if self.id:
            old_user = User.objects.get(id=self.id)
            if self.image != old_user.image:
                if old_user.image:
                    os.remove(os.path.join(settings.MEDIA_ROOT, old_user.image.path))
        super(User, self).save(*args, **kwargs)

    def add_points(self, points, detail):
        self.points += points
        self.save()
        pointlog, _ = PointLog.objects.get_or_create(user=self)
        point_log_item = PointLogItem()
        point_log_item.point_log = pointlog
        point_log_item.type = True
        point_log_item.type_detail = detail
        point_log_item.amount = points
        point_log_item.save()

    def subtract_points(self, points, detail):
        self.points -= points
        self.save()
        pointlog, _ = PointLog.objects.get_or_create(user=self)
        point_log_item = PointLogItem()
        point_log_item.point_log = pointlog
        point_log_item.type = False
        point_log_item.type_detail = detail
        point_log_item.amount = points
        point_log_item.save()

    def get_followings_and_followers(self):
        followings_and_followers = set(self.followings.all()) | set(
            self.followers.all()
        )
        followings_and_followers.discard(self)
        return followings_and_followers


class PointLog(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="point_logs"
    )


class PointLogItem(models.Model):
    point_log = models.ForeignKey(
        PointLog, on_delete=models.CASCADE, related_name="point_log_itmes"
    )
    type = models.BooleanField(default=False)  # False일 경우 차감, True일 경우 적립
    type_detail = models.CharField(max_length=10)  # 적립, 사용, 참여, 참여취소
    amount = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

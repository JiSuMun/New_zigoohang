from datetime import date, datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from pytz import timezone

from .forms import (
    CertificationForm,
    ChallengeForm,
    ChallengeImage_DeleteImageForm,
    ChallengeImageForm,
)
from .models import Certification, Challenge, ChallengeImage


def staff_only(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        else:
            return redirect("main")

    return wrapper


def index(request):
    q = request.GET.get("q", "")

    if q == "진행중인챌린지":
        challenges = Challenge.objects.filter(end_date__gt=date.today()).order_by(
            "-created"
        )
    elif q == "마감된챌린지":
        challenges = Challenge.objects.filter(end_date__lte=date.today()).order_by(
            "-created"
        )
    else:
        challenges = Challenge.objects.all().order_by("-created")
    paginator = Paginator(challenges, 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    context = {
        "page_obj": page_obj,
        "q": q,
    }
    return render(request, "challenges/index.html", context)


def detail(request, challenge_pk):
    challenge = Challenge.objects.get(pk=challenge_pk)
    seoul_timezone = timezone(settings.TIME_ZONE)
    in_progress = (
        challenge.start_date.date()
        <= datetime.now(seoul_timezone).date()
        <= challenge.end_date.date()
    )
    challenge_images = ChallengeImage.objects.filter(challenge=challenge_pk)
    certification_form = CertificationForm()
    certifications = challenge.certifications.all()
    days_remaining = calculate_remaining_days(challenge.end_date.date())
    ended = False
    is_participant = request.user in challenge.participants.all()
    certified_users = (
        get_user_model().objects.filter(certification__challenge=challenge).distinct()
    )
    user_has_certified = False
    if request.user.is_authenticated:
        user_has_certified = Certification.objects.filter(
            user=request.user, challenge=challenge
        ).exists()

    if days_remaining == 0:
        d_day_string = "D-DAY"
    elif days_remaining <= 0:
        ended = True
        d_day_string = "종료되었습니다."
    else:
        d_day_string = f"D-{days_remaining}"
    u_certification_forms = []

    for certification in certifications:
        u_certification_form = (
            certification,
            CertificationForm(instance=certification),
        )
        u_certification_forms.append(u_certification_form)

    context = {
        "challenge": challenge,
        "challenge_images": challenge_images,
        "certification_form": certification_form,
        "u_certification_forms": u_certification_forms,
        "certifications": certifications,
        "days_remaining": days_remaining,
        "ended": ended,
        "d_day_string": d_day_string,
        "user_has_certified": user_has_certified,
        "certified_users": certified_users,
        "is_participant": is_participant,
        "in_progress": in_progress,
    }

    return render(request, "challenges/detail.html", context)


@staff_only
@login_required
def create(request):
    if not request.user.is_staff:
        return HttpResponseForbidden()

    Challenge_form = ChallengeForm()
    image_form = ChallengeImageForm()

    if request.method == "POST":
        Challenge_form = ChallengeForm(request.POST, request.FILES)
        files = request.FILES.getlist("image")

        if Challenge_form.is_valid():
            challenge = Challenge_form.save(commit=False)
            challenge.creator = request.user
            challenge.save()
            for i in files:
                ChallengeImage.objects.create(image=i, challenge=challenge)
            return redirect("challenges:detail", challenge.pk)
    context = {
        "form": Challenge_form,
        "image_form": image_form,
    }

    return render(request, "challenges/create.html", context)


@staff_only
@login_required
def update(request, challenge_pk):
    if not request.user.is_staff:
        return HttpResponseForbidden()

    challenge = Challenge.objects.get(pk=challenge_pk)
    if request.method == "POST":
        challenge_form = ChallengeForm(request.POST, instance=challenge)
        files = request.FILES.getlist("image")
        delete_ids = request.POST.getlist("delete_images")
        delete_image_form = ChallengeImage_DeleteImageForm(
            challenge=challenge, data=request.POST
        )

        if challenge_form.is_valid() and delete_image_form.is_valid():
            challenge = challenge_form.save(commit=False)
            challenge.user = request.user
            challenge.save()
            for delete_id in delete_ids:
                challenge.challengeimage_set.filter(pk=delete_id).delete()

            for i in files:
                ChallengeImage.objects.create(image=i, challenge=challenge)

            return redirect("challenges:detail", challenge.pk)

    else:
        challenge_form = ChallengeForm(instance=challenge)
        delete_image_form = ChallengeImage_DeleteImageForm(challenge=challenge)

    if challenge.challengeimage_set.exists():
        image_form = ChallengeImageForm(instance=challenge.challengeimage_set.first())

    else:
        image_form = ChallengeImageForm()

    context = {
        "challenge": challenge,
        "challenge_form": challenge_form,
        "image_form": image_form,
        "delete_image_form": delete_image_form,
    }

    return render(request, "challenges/update.html", context)


@staff_only
@login_required
def delete(request, challenge_pk):
    challenge = Challenge.objects.get(pk=challenge_pk)
    if request.user == challenge.creator:
        challenge.delete()
    return redirect("challenges:index")


@login_required
def certification_create(request, challenge_pk):
    challenge = Challenge.objects.get(pk=challenge_pk)

    if request.method == "POST":
        certification_form = CertificationForm(request.POST, request.FILES)
        if certification_form.is_valid():
            certification = certification_form.save(commit=False)
            certification.user = request.user
            certification.challenge = challenge
            certification.save()
            request.user.add_points(500, "참여")

            return redirect("challenges:detail", challenge_pk)

    else:
        certification_form = CertificationForm()

    context = {
        "certification_form": certification_form,
        "challenge": challenge,
    }
    return render(request, "challenges/detail.html", context)


@login_required
def certification_update(request, challenge_pk, certification_pk):
    challenge = Challenge.objects.get(pk=challenge_pk)
    certification = Certification.objects.get(pk=certification_pk)
    u_certification_form = CertificationForm(instance=certification)

    if request.method == "POST":
        u_certification_form = CertificationForm(
            request.POST, request.FILES, instance=certification
        )

        if u_certification_form.is_valid():
            certification = u_certification_form.save(commit=False)
            certification.challenge = challenge
            certification.user = request.user
            certification.save()

        return redirect("challenges:detail", challenge.pk)

    context = {
        "challenge": challenge,
        "certification": certification,
        "u_certification_form": u_certification_form,
    }
    return render(request, "challenges/detail.html", context)


@login_required
def certification_delete(request, challenge_pk, certification_pk):
    certification = Certification.objects.filter(pk=certification_pk).first()
    if certification and request.user == certification.user:
        certification.delete()
        request.user.subtract_points(500, "참여취소")
        request.user.save()

    return redirect("challenges:detail", challenge_pk)


@login_required
def participation(request, challenge_pk):
    User = get_user_model()
    challenge = Challenge.objects.get(pk=challenge_pk)

    is_certified = Certification.objects.filter(
        challenge=challenge, user=request.user
    ).exists()

    is_participating = False
    if request.user in challenge.participants.all():
        challenge.participants.remove(request.user)
        is_participating = False
    else:
        challenge.participants.add(request.user)
        is_participating = True

    context = {
        "is_participating": is_participating,
        "participants_count": challenge.participants.count(),
        "is_certified": is_certified,
    }
    return JsonResponse(context)


def calculate_remaining_days(end_date):
    seoul_timezone = timezone(settings.TIME_ZONE)
    current_time = datetime.now(seoul_timezone)

    end_date_time = datetime.combine(
        end_date, datetime.min.time(), tzinfo=seoul_timezone
    )
    remaining_time = end_date_time - current_time
    days_remaining = remaining_time.days + 1

    return days_remaining


def join_challenge(request, challenge_pk):
    challenge = Challenge.objects.filter(pk=challenge_pk).first()
    if challenge:
        challenge.participants.add(request.user)  # 참가자 추가
        challenge.save()
    return redirect("challenges:detail", challenge_pk)


def leave_challenge(request, challenge_pk):
    challenge = Challenge.objects.filter(pk=challenge_pk).first()
    if challenge:
        challenge.participants.remove(request.user)  # 참가자 제거
        challenge.save()
    return redirect("challenges:detail", challenge_pk)


def isthisuserjoined(user, challenge):
    return user.participating_challenges.filter(pk=challenge.pk).exists()

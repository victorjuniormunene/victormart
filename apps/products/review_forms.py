from django import forms

from .models import ProductReview


class ProductReviewForm(forms.ModelForm):
    class Meta:
        model = ProductReview
        fields = ('rating', 'comment')
        widgets = {
            'rating': forms.Select(
                choices=[(rating, f'{rating} star{"s" if rating != 1 else ""}') for rating in range(5, 0, -1)]
            ),
            'comment': forms.Textarea(attrs={
                'rows': 4,
                'maxlength': 1000,
                'placeholder': 'Share details about your product experience',
            }),
        }
